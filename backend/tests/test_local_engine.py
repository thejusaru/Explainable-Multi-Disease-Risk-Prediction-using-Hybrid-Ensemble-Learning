"""Tests for the local (Ollama) engine.

Focused on `_coerce_payload` and `_parse_json` — the repair logic that exists
specifically because small models get structured output wrong in predictable
ways. Ollama itself is never called here.
"""

from __future__ import annotations

import pytest

from app.engines.base import RiskEngineError
from app.engines.local_engine import LocalRiskEngine, _normalise_level
from app.models.schemas import PROJECTION_AGES


def _condition(projections: list[dict], **overrides) -> dict:
    condition = {
        "condition": "Type 2 diabetes",
        "category": "metabolic",
        "projections": projections,
        "drivers": ["Family history"],
        "protective_factors": [],
        "rationale": "Family history and elevated HbA1c.",
        "modifiable": True,
        "confidence": "medium",
    }
    condition.update(overrides)
    return condition


def _full_projections() -> list[dict]:
    return [
        {"age": age, "probability": p, "level": "low"}
        for age, p in zip(PROJECTION_AGES, [0.02, 0.04, 0.07, 0.11, 0.18])
    ]


# --- JSON parsing -----------------------------------------------------------


def test_parses_clean_json():
    parsed = LocalRiskEngine._parse_json('{"summary": "ok"}')
    assert parsed["summary"] == "ok"


def test_strips_markdown_fences():
    """Local models emit fences despite format:json being requested."""
    raw = '```json\n{"summary": "fenced"}\n```'
    assert LocalRiskEngine._parse_json(raw)["summary"] == "fenced"


def test_recovers_json_from_surrounding_prose():
    raw = 'Here is the assessment:\n{"summary": "extracted"}\nHope that helps!'
    assert LocalRiskEngine._parse_json(raw)["summary"] == "extracted"


def test_unparseable_output_raises():
    with pytest.raises(RiskEngineError, match="valid JSON"):
        LocalRiskEngine._parse_json("I cannot help with that request.")


# --- Payload repair ---------------------------------------------------------


def test_percentages_are_rescaled_to_proportions():
    """A 7B model writing 15 instead of 0.15 is the most common single error."""
    payload = {
        "conditions": [
            _condition(
                [
                    {"age": 25, "probability": 2, "level": "low"},
                    {"age": 30, "probability": 5, "level": "moderate"},
                    {"age": 35, "probability": 12, "level": "moderate"},
                    {"age": 40, "probability": 22, "level": "high"},
                    {"age": 45, "probability": 35, "level": "very_high"},
                ]
            )
        ]
    }
    repaired = LocalRiskEngine._coerce_payload(payload)
    values = [p["probability"] for p in repaired["conditions"][0]["projections"]]
    assert values == [0.02, 0.05, 0.12, 0.22, 0.35]


def test_missing_age_buckets_are_filled_forward():
    """Carry the last value forward rather than inventing an interpolated trend."""
    payload = {
        "conditions": [
            _condition(
                [
                    {"age": 25, "probability": 0.02, "level": "low"},
                    {"age": 45, "probability": 0.30, "level": "very_high"},
                ]
            )
        ]
    }
    repaired = LocalRiskEngine._coerce_payload(payload)
    projections = repaired["conditions"][0]["projections"]

    assert [p["age"] for p in projections] == list(PROJECTION_AGES)
    assert [p["probability"] for p in projections] == [0.02, 0.02, 0.02, 0.02, 0.30]


def test_unexpected_ages_are_dropped():
    payload = {
        "conditions": [
            _condition(
                [
                    {"age": 25, "probability": 0.02, "level": "low"},
                    {"age": 50, "probability": 0.40, "level": "very_high"},
                    {"age": 60, "probability": 0.55, "level": "very_high"},
                ]
            )
        ]
    }
    repaired = LocalRiskEngine._coerce_payload(payload)
    assert [p["age"] for p in repaired["conditions"][0]["projections"]] == list(
        PROJECTION_AGES
    )


def test_invalid_level_is_derived_from_probability():
    payload = {
        "conditions": [
            _condition(
                [
                    {"age": 25, "probability": 0.02, "level": "minimal"},
                    {"age": 30, "probability": 0.08, "level": "MODERATE"},
                    {"age": 35, "probability": 0.20, "level": "very high"},
                    {"age": 40, "probability": 0.35, "level": None},
                    {"age": 45, "probability": 0.45, "level": "catastrophic"},
                ]
            )
        ]
    }
    repaired = LocalRiskEngine._coerce_payload(payload)
    levels = [p["level"] for p in repaired["conditions"][0]["projections"]]
    assert levels == ["low", "moderate", "very_high", "very_high", "very_high"]


def test_missing_optional_fields_get_defaults():
    payload = {
        "conditions": [
            {"condition": "Hypertension", "projections": _full_projections()}
        ]
    }
    repaired = LocalRiskEngine._coerce_payload(payload)
    condition = repaired["conditions"][0]

    assert condition["category"] == "general"
    assert condition["drivers"] == []
    assert condition["modifiable"] is True
    assert condition["confidence"] == "low"


def test_invalid_priority_falls_back_to_medium():
    payload = {
        "conditions": [_condition(_full_projections())],
        "recommendations": [
            {"title": "Exercise", "priority": "CRITICAL!!"},
            {"title": "Diet", "priority": "urgent"},
            {"detail": "no title, dropped"},
        ],
    }
    repaired = LocalRiskEngine._coerce_payload(payload)
    recommendations = repaired["recommendations"]

    assert len(recommendations) == 2
    assert recommendations[0]["priority"] == "medium"
    assert recommendations[1]["priority"] == "urgent"


def test_empty_conditions_list_is_rejected():
    with pytest.raises(RiskEngineError, match="no conditions"):
        LocalRiskEngine._coerce_payload({"conditions": []})


def test_conditions_without_usable_projections_are_rejected():
    payload = {"conditions": [_condition([{"age": 99, "probability": 0.5}])]}
    with pytest.raises(RiskEngineError, match="no usable conditions"):
        LocalRiskEngine._coerce_payload(payload)


def test_unnamed_conditions_are_skipped():
    payload = {
        "conditions": [
            _condition(_full_projections(), condition=""),
            _condition(_full_projections(), condition="Hypertension"),
        ]
    }
    repaired = LocalRiskEngine._coerce_payload(payload)
    assert len(repaired["conditions"]) == 1
    assert repaired["conditions"][0]["condition"] == "Hypertension"


def test_probabilities_are_clamped_to_range():
    payload = {
        "conditions": [
            _condition(
                [
                    {"age": 25, "probability": -0.5, "level": "low"},
                    {"age": 30, "probability": 0.2, "level": "high"},
                    {"age": 35, "probability": 0.3, "level": "high"},
                    {"age": 40, "probability": 0.4, "level": "high"},
                    {"age": 45, "probability": 250, "level": "very_high"},
                ]
            )
        ]
    }
    repaired = LocalRiskEngine._coerce_payload(payload)
    values = [p["probability"] for p in repaired["conditions"][0]["projections"]]
    assert all(0.0 <= v <= 1.0 for v in values), values


# --- Level derivation -------------------------------------------------------


@pytest.mark.parametrize(
    "probability,expected",
    [
        (0.01, "low"),
        (0.049, "low"),
        (0.05, "moderate"),
        (0.14, "moderate"),
        (0.15, "high"),
        (0.29, "high"),
        (0.30, "very_high"),
        (0.90, "very_high"),
    ],
)
def test_level_thresholds_match_the_prompt(probability, expected):
    assert _normalise_level(None, probability) == expected


def test_valid_level_is_preserved_over_derivation():
    # An explicit, valid level wins even if it disagrees with the threshold.
    assert _normalise_level("low", 0.9) == "low"


# --- Duplicate-curve detection ----------------------------------------------
#
# Observed with qwen2.5:7b: the model emits one probability curve and reuses it
# for every condition. Structurally valid, clinically meaningless.


def _assessment_with(curves: list[list[float]]):
    from app.models.schemas import PatientProfile, RiskAssessment

    return RiskAssessment(
        profile=PatientProfile(age=34),
        conditions=[
            {
                "condition": f"Condition {i}",
                "category": "general",
                "projections": [
                    {"age": age, "probability": p, "level": "low"}
                    for age, p in zip(PROJECTION_AGES, curve)
                ],
                "drivers": [],
                "protective_factors": [],
                "rationale": "",
                "modifiable": True,
                "confidence": "low",
            }
            for i, curve in enumerate(curves)
        ],
        engine="local",
    )


def test_identical_curves_are_flagged_to_the_user():
    shared = [0.02, 0.04, 0.08, 0.16, 0.27]
    assessment = _assessment_with([shared, list(shared), [0.1, 0.2, 0.3, 0.4, 0.5]])

    LocalRiskEngine._flag_duplicate_curves(assessment)

    assert assessment.missing_data
    assert "identical probabilities" in assessment.missing_data[0]
    assert "Condition 0" in assessment.missing_data[0]
    assert "Condition 1" in assessment.missing_data[0]


def test_distinct_curves_are_not_flagged():
    assessment = _assessment_with(
        [
            [0.02, 0.04, 0.08, 0.16, 0.27],
            [0.10, 0.14, 0.18, 0.22, 0.26],
            [0.18, 0.24, 0.31, 0.38, 0.46],
        ]
    )

    LocalRiskEngine._flag_duplicate_curves(assessment)

    assert assessment.missing_data == []


def test_single_condition_is_never_flagged():
    assessment = _assessment_with([[0.02, 0.04, 0.08, 0.16, 0.27]])
    LocalRiskEngine._flag_duplicate_curves(assessment)
    assert assessment.missing_data == []


# --- Guard rails ------------------------------------------------------------


@pytest.mark.asyncio
async def test_image_only_report_is_rejected():
    """Most local text models cannot see; fail loudly instead of analysing blank."""
    from app.parsers.extract import ExtractedReport

    engine = LocalRiskEngine(model="qwen2.5:7b")
    report = ExtractedReport(image_base64="aGk=", image_media_type="image/png")

    with pytest.raises(RiskEngineError, match="cannot read images"):
        await engine.assess(report=report)


@pytest.mark.asyncio
async def test_no_input_is_rejected():
    engine = LocalRiskEngine(model="qwen2.5:7b")
    with pytest.raises(RiskEngineError, match="Provide either"):
        await engine.assess()

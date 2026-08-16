"""Tests for the LLM engine's request building and response post-processing.

The Claude client is stubbed throughout — these cover our own logic, not the
model's behaviour.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.engines.base import RiskEngineError
from app.engines.llm_engine import LLMRiskEngine
from app.models.schemas import Confidence, PatientProfile, SmokingStatus
from app.parsers.extract import ExtractedReport


def _valid_payload(**overrides) -> dict:
    payload = {
        "summary": "Elevated cardiovascular risk driven by smoking and blood pressure.",
        "conditions": [
            {
                "condition": "Coronary artery disease",
                "category": "cardiovascular",
                "projections": [
                    {"age": 25, "probability": 0.01, "level": "low"},
                    {"age": 30, "probability": 0.03, "level": "low"},
                    {"age": 35, "probability": 0.07, "level": "moderate"},
                    {"age": 40, "probability": 0.14, "level": "moderate"},
                    {"age": 45, "probability": 0.22, "level": "high"},
                ],
                "drivers": ["Current smoker", "Systolic BP 148 mmHg"],
                "protective_factors": [],
                "rationale": "Smoking and hypertension are the dominant drivers.",
                "modifiable": True,
                "confidence": "medium",
            }
        ],
        "recommendations": [
            {
                "title": "Stop smoking",
                "detail": "The single highest-impact change available.",
                "priority": "urgent",
                "targets": ["Coronary artery disease"],
            }
        ],
        "missing_data": [],
    }
    payload.update(overrides)
    return payload


class _StubMessages:
    def __init__(self, payload: dict, stop_reason: str = "end_turn"):
        self._payload = payload
        self._stop_reason = stop_reason
        self.last_request: dict | None = None

    async def create(self, **kwargs):
        self.last_request = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(self._payload))],
            stop_reason=self._stop_reason,
            stop_details=None,
        )


class _StubClient:
    def __init__(self, payload: dict, stop_reason: str = "end_turn"):
        self.messages = _StubMessages(payload, stop_reason)


def _engine(payload: dict, stop_reason: str = "end_turn") -> LLMRiskEngine:
    return LLMRiskEngine(client=_StubClient(payload, stop_reason))


@pytest.mark.asyncio
async def test_assess_returns_a_validated_assessment():
    engine = _engine(_valid_payload())
    profile = PatientProfile(age=34, smoking=SmokingStatus.current, systolic_bp=148)

    assessment = await engine.assess(profile=profile)

    assert assessment.engine == "llm"
    assert len(assessment.conditions) == 1
    assert [p.age for p in assessment.conditions[0].projections] == [25, 30, 35, 40, 45]
    assert assessment.recommendations[0].priority == "urgent"


@pytest.mark.asyncio
async def test_assess_requires_some_input():
    engine = _engine(_valid_payload())
    with pytest.raises(RiskEngineError, match="Provide either"):
        await engine.assess()


@pytest.mark.asyncio
async def test_decreasing_probabilities_are_clamped_monotonic():
    """Cumulative incidence cannot fall with age, so a dip must be corrected."""
    payload = _valid_payload()
    payload["conditions"][0]["projections"] = [
        {"age": 25, "probability": 0.10, "level": "moderate"},
        {"age": 30, "probability": 0.04, "level": "low"},
        {"age": 35, "probability": 0.12, "level": "moderate"},
        {"age": 40, "probability": 0.08, "level": "moderate"},
        {"age": 45, "probability": 0.30, "level": "very_high"},
    ]
    engine = _engine(payload)

    assessment = await engine.assess(profile=PatientProfile(age=30))
    values = [p.probability for p in assessment.conditions[0].projections]

    assert values == sorted(values), f"expected non-decreasing, got {values}"
    assert values == [0.10, 0.10, 0.12, 0.12, 0.30]


@pytest.mark.asyncio
async def test_sparse_profile_downgrades_high_confidence():
    payload = _valid_payload()
    payload["conditions"][0]["confidence"] = "high"
    engine = _engine(payload)

    # Age only — nothing else known.
    assessment = await engine.assess(profile=PatientProfile(age=30))

    assert assessment.conditions[0].confidence == Confidence.medium
    assert any("Limited input data" in note for note in assessment.missing_data)


@pytest.mark.asyncio
async def test_rich_profile_keeps_high_confidence():
    payload = _valid_payload()
    payload["conditions"][0]["confidence"] = "high"
    engine = _engine(payload)

    profile = PatientProfile(
        age=34,
        height_cm=178,
        weight_kg=92,
        systolic_bp=148,
        smoking=SmokingStatus.current,
    )
    assessment = await engine.assess(profile=profile)

    assert assessment.conditions[0].confidence == Confidence.high


@pytest.mark.asyncio
async def test_user_supplied_values_beat_model_extraction():
    payload = _valid_payload(extracted_profile={"age": 99, "sex": "female"})
    engine = _engine(payload)

    assessment = await engine.assess(profile=PatientProfile(age=34))

    # The typed age wins; the extracted sex fills a gap the user left blank.
    assert assessment.profile.age == 34
    assert assessment.profile.sex is not None
    assert assessment.profile.sex.value == "female"


@pytest.mark.asyncio
async def test_report_only_path_uses_extracted_profile():
    payload = _valid_payload(
        extracted_profile={"age": 41, "sex": "male", "systolic_bp": 150}
    )
    engine = _engine(payload)

    assessment = await engine.assess(
        report=ExtractedReport(text="Some report text with values.")
    )

    assert assessment.profile.age == 41
    assert assessment.profile.systolic_bp == 150


@pytest.mark.asyncio
async def test_report_without_a_derivable_age_is_an_error():
    engine = _engine(_valid_payload())  # no extracted_profile at all
    with pytest.raises(RiskEngineError, match="age"):
        await engine.assess(report=ExtractedReport(text="Illegible scan."))


@pytest.mark.asyncio
async def test_refusal_is_surfaced_not_parsed():
    engine = _engine(_valid_payload(), stop_reason="refusal")
    with pytest.raises(RiskEngineError, match="declined"):
        await engine.assess(profile=PatientProfile(age=30))


@pytest.mark.asyncio
async def test_truncated_response_is_surfaced():
    engine = _engine(_valid_payload(), stop_reason="max_tokens")
    with pytest.raises(RiskEngineError, match="cut short"):
        await engine.assess(profile=PatientProfile(age=30))


@pytest.mark.asyncio
async def test_malformed_projection_set_is_rejected():
    payload = _valid_payload()
    payload["conditions"][0]["projections"] = [
        {"age": 25, "probability": 0.01, "level": "low"},
    ]
    engine = _engine(payload)

    with pytest.raises(RiskEngineError, match="inconsistent"):
        await engine.assess(profile=PatientProfile(age=30))


@pytest.mark.asyncio
async def test_missing_credentials_give_an_actionable_error():
    """The SDK raises a bare TypeError with no key set; don't leak it as a 500."""

    class _NoCredsMessages:
        async def create(self, **kwargs):
            raise TypeError(
                "Could not resolve authentication method. Expected one of "
                "api_key, auth_token, or credentials to be set."
            )

    engine = LLMRiskEngine(client=SimpleNamespace(messages=_NoCredsMessages()))

    with pytest.raises(RiskEngineError, match="ANTHROPIC_API_KEY"):
        await engine.assess(profile=PatientProfile(age=34))


@pytest.mark.asyncio
async def test_unrelated_type_errors_are_not_swallowed():
    """Only the credential TypeError is translated; real bugs must propagate."""

    class _BuggyMessages:
        async def create(self, **kwargs):
            raise TypeError("unsupported operand type(s) for +: 'int' and 'str'")

    engine = LLMRiskEngine(client=SimpleNamespace(messages=_BuggyMessages()))

    with pytest.raises(TypeError, match="unsupported operand"):
        await engine.assess(profile=PatientProfile(age=34))


@pytest.mark.asyncio
async def test_image_report_is_sent_as_an_image_block():
    engine = _engine(_valid_payload())
    client = engine._client

    await engine.assess(
        profile=PatientProfile(age=34),
        report=ExtractedReport(
            image_base64="aGVsbG8=", image_media_type="image/png"
        ),
    )

    content = client.messages.last_request["messages"][0]["content"]
    image_blocks = [b for b in content if b["type"] == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["source"]["media_type"] == "image/png"


@pytest.mark.asyncio
async def test_unknown_fields_are_omitted_from_the_prompt():
    """Rendering 'Smoking: None' would read as an assertion of non-smoking."""
    engine = _engine(_valid_payload())
    client = engine._client

    await engine.assess(profile=PatientProfile(age=34))

    text = "".join(
        b["text"]
        for b in client.messages.last_request["messages"][0]["content"]
        if b["type"] == "text"
    )
    assert "Age: 34" in text
    assert "Smoking:" not in text

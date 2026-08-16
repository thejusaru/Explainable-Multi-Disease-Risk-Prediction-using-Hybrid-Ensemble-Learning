"""Tests for the shared data contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    ConditionRisk,
    PatientProfile,
    RiskLevel,
    SmokingStatus,
)


def _projections(*probabilities: float) -> list[dict]:
    ages = (25, 30, 35, 40, 45)
    return [
        {"age": age, "probability": p, "level": RiskLevel.low}
        for age, p in zip(ages, probabilities)
    ]


def test_bmi_computed_from_height_and_weight():
    profile = PatientProfile(age=40, height_cm=180, weight_kg=81)
    assert profile.bmi == 25.0


def test_bmi_is_none_without_measurements():
    assert PatientProfile(age=40).bmi is None


def test_known_field_count_tracks_supplied_data():
    sparse = PatientProfile(age=30)
    rich = PatientProfile(
        age=30,
        height_cm=175,
        weight_kg=70,
        systolic_bp=120,
        smoking=SmokingStatus.never,
        family_history=["type 2 diabetes"],
    )
    assert sparse.known_field_count() == 0
    assert rich.known_field_count() == 5


def test_condition_requires_all_five_age_buckets():
    with pytest.raises(ValidationError, match="must cover exactly"):
        ConditionRisk(
            condition="Type 2 diabetes",
            category="metabolic",
            projections=[
                {"age": 25, "probability": 0.01, "level": RiskLevel.low},
                {"age": 30, "probability": 0.02, "level": RiskLevel.low},
            ],
        )


def test_condition_rejects_unexpected_age():
    with pytest.raises(ValidationError, match="must cover exactly"):
        ConditionRisk(
            condition="Hypertension",
            category="cardiovascular",
            projections=[
                {"age": 25, "probability": 0.01, "level": RiskLevel.low},
                {"age": 30, "probability": 0.02, "level": RiskLevel.low},
                {"age": 35, "probability": 0.03, "level": RiskLevel.low},
                {"age": 40, "probability": 0.04, "level": RiskLevel.low},
                {"age": 50, "probability": 0.05, "level": RiskLevel.low},
            ],
        )


def test_condition_sorts_projections_by_age():
    condition = ConditionRisk(
        condition="Hypertension",
        category="cardiovascular",
        projections=[
            {"age": 45, "probability": 0.20, "level": RiskLevel.high},
            {"age": 25, "probability": 0.02, "level": RiskLevel.low},
            {"age": 35, "probability": 0.09, "level": RiskLevel.moderate},
            {"age": 30, "probability": 0.05, "level": RiskLevel.moderate},
            {"age": 40, "probability": 0.14, "level": RiskLevel.moderate},
        ],
    )
    assert [p.age for p in condition.projections] == [25, 30, 35, 40, 45]


def test_probability_must_be_a_proportion():
    with pytest.raises(ValidationError):
        ConditionRisk(
            condition="Lung cancer",
            category="oncologic",
            # 45 as a percentage rather than a proportion — a plausible model slip.
            projections=_projections(0.01, 0.02, 0.03, 0.04, 45.0),
        )


def test_implausible_vitals_are_rejected():
    with pytest.raises(ValidationError):
        PatientProfile(age=40, systolic_bp=900)
    with pytest.raises(ValidationError):
        PatientProfile(age=-5)

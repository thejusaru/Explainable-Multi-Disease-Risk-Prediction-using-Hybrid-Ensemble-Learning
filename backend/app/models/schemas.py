"""Data contracts shared by the ingestion layer, the risk engine and the API.

The schemas here are deliberately engine-agnostic: `RiskEngine` implementations
return `RiskAssessment` regardless of whether the numbers come from an LLM or a
published clinical model, so the frontend never has to care which one ran.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# The ages the product reports on. Kept as a module constant because both the
# prompt builder and the response validator need to agree on it.
PROJECTION_AGES: tuple[int, ...] = (25, 30, 35, 40, 45)


class Sex(str, Enum):
    male = "male"
    female = "female"
    other = "other"


class SmokingStatus(str, Enum):
    never = "never"
    former = "former"
    current = "current"


class AlcoholUse(str, Enum):
    none = "none"
    occasional = "occasional"
    moderate = "moderate"
    heavy = "heavy"


class ActivityLevel(str, Enum):
    sedentary = "sedentary"
    light = "light"
    moderate = "moderate"
    active = "active"


class ShiftPattern(str, Enum):
    """Night/rotating shift work is an independent risk factor the user called out."""

    day = "day"
    rotating = "rotating"
    night = "night"


class StressLevel(str, Enum):
    low = "low"
    moderate = "moderate"
    high = "high"
    severe = "severe"


class LabResult(BaseModel):
    """A single measured value pulled off a report, with its units preserved.

    Units are kept as free text rather than normalised because labs report the
    same analyte in different units (mg/dL vs mmol/L) and silently coercing them
    is how you get a decimal-point error in a medical context.
    """

    name: str
    value: float
    unit: str | None = None
    reference_range: str | None = None
    flag: Literal["low", "normal", "high"] | None = None


class PatientProfile(BaseModel):
    """Everything the risk engine is allowed to reason from.

    Every field except `age` is optional: real reports are incomplete, and the
    engine is expected to say so rather than invent values.
    """

    age: int = Field(ge=0, le=120)
    sex: Sex | None = None

    height_cm: float | None = Field(default=None, gt=0, le=280)
    weight_kg: float | None = Field(default=None, gt=0, le=500)

    systolic_bp: int | None = Field(default=None, ge=50, le=300)
    diastolic_bp: int | None = Field(default=None, ge=30, le=200)

    smoking: SmokingStatus | None = None
    alcohol: AlcoholUse | None = None
    activity: ActivityLevel | None = None
    shift_pattern: ShiftPattern | None = None
    stress_level: StressLevel | None = None
    sleep_hours: float | None = Field(default=None, ge=0, le=24)

    family_history: list[str] = Field(default_factory=list)
    existing_conditions: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)

    labs: list[LabResult] = Field(default_factory=list)
    raw_report_text: str | None = None

    @property
    def bmi(self) -> float | None:
        if self.height_cm and self.weight_kg:
            metres = self.height_cm / 100
            return round(self.weight_kg / (metres * metres), 1)
        return None

    def known_field_count(self) -> int:
        """How much we actually know. Drives the confidence signal in the UI."""
        tracked = (
            self.sex,
            self.height_cm,
            self.weight_kg,
            self.systolic_bp,
            self.smoking,
            self.alcohol,
            self.activity,
            self.shift_pattern,
            self.stress_level,
            self.sleep_hours,
        )
        count = sum(1 for value in tracked if value is not None)
        count += 1 if self.family_history else 0
        count += 1 if self.existing_conditions else 0
        count += 1 if self.labs else 0
        return count


class RiskLevel(str, Enum):
    low = "low"
    moderate = "moderate"
    high = "high"
    very_high = "very_high"


class Confidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class RiskProjection(BaseModel):
    """One condition's estimated probability at one age."""

    age: int
    probability: float = Field(ge=0.0, le=1.0)
    level: RiskLevel


class ConditionRisk(BaseModel):
    """A single condition tracked across the whole projection timeline."""

    condition: str
    category: str
    projections: list[RiskProjection]
    drivers: list[str] = Field(
        default_factory=list,
        description="Which profile facts pushed this risk up. Shown to the user.",
    )
    protective_factors: list[str] = Field(default_factory=list)
    rationale: str = ""
    modifiable: bool = True
    confidence: Confidence = Confidence.low

    @field_validator("projections")
    @classmethod
    def _projections_cover_expected_ages(
        cls, projections: list[RiskProjection]
    ) -> list[RiskProjection]:
        """Guard against a model that drops or invents an age bucket.

        Without this the frontend chart would silently render a gap-toothed
        timeline instead of surfacing that the response was malformed.
        """
        ages = sorted(p.age for p in projections)
        if ages != sorted(PROJECTION_AGES):
            raise ValueError(
                f"projections must cover exactly {list(PROJECTION_AGES)}, got {ages}"
            )
        return sorted(projections, key=lambda p: p.age)


class Recommendation(BaseModel):
    title: str
    detail: str
    priority: Literal["urgent", "high", "medium", "low"] = "medium"
    targets: list[str] = Field(
        default_factory=list, description="Condition names this action reduces risk for."
    )


class RiskAssessment(BaseModel):
    """The complete engine output. This is what the frontend renders."""

    profile: PatientProfile
    conditions: list[ConditionRisk]
    recommendations: list[Recommendation] = Field(default_factory=list)
    summary: str = ""
    missing_data: list[str] = Field(
        default_factory=list,
        description="Fields that would materially improve the estimate if supplied.",
    )
    engine: str = Field(description="Which RiskEngine produced this, for auditability.")
    model: str | None = None
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    disclaimer: str = (
        "This is a statistical risk-estimation tool, not a medical diagnosis. "
        "Estimates are generated by an AI language model and are not reproducible "
        "or clinically validated. Do not use them to make treatment decisions. "
        "Consult a qualified clinician about any health concern."
    )


class AnalyzeResponse(BaseModel):
    assessment: RiskAssessment
    extraction_notes: list[str] = Field(
        default_factory=list,
        description="What the parser did or could not do with the uploaded file.",
    )


class ExtractResponse(BaseModel):
    """Result of reading a report *without* running a risk assessment.

    Lets the user review and correct what was parsed before it reaches the risk
    model — a misread blood pressure should be caught by a human, not silently
    folded into an estimate.
    """

    profile: PatientProfile | None = Field(
        default=None,
        description="Values read from the report. None when nothing usable was found.",
    )
    fields_found: list[str] = Field(
        default_factory=list,
        description="Human-readable names of the fields that were populated.",
    )
    notes: list[str] = Field(default_factory=list)
    requires_manual_entry: bool = Field(
        default=False,
        description="True when the report could not be parsed into a profile.",
    )
    report_text: str | None = Field(
        default=None,
        description="Extracted text, echoed back so analysis need not re-parse.",
    )
    image_base64: str | None = None
    image_media_type: str | None = None

"""LLM-backed risk engine.

Claude reads the profile/report and returns a full risk timeline. Structured
outputs pin the response shape, so the only failure modes left are refusals and
transport errors — not JSON parsing.

Known limitation, by design: output is **not reproducible**. Two runs on the
same input can differ by several percentage points. Sampling parameters are
rejected on Opus 5, so there is no `temperature=0` lever to pull; if you need
stable numbers, implement a clinical-model `RiskEngine` alongside this one.
"""

from __future__ import annotations

import json
import logging

import anthropic

from app.models.schemas import (
    PROJECTION_AGES,
    Confidence,
    PatientProfile,
    RiskAssessment,
)
from app.engines.base import RiskEngine, RiskEngineError
from app.parsers.extract import ExtractedReport

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5"

SYSTEM_PROMPT = """\
You are a health risk-estimation engine. You read a patient profile and produce \
calibrated probability estimates for future disease onset at ages \
25, 30, 35, 40 and 45.

Ground every estimate in established epidemiology. Where a published risk model \
applies to the data you were given (Framingham or ASCVD for cardiovascular \
disease, FINDRISC for type 2 diabetes, GAIL for breast cancer), reason in line \
with it and say so in the rationale.

Rules you must follow:

- Report absolute lifetime-to-date probability of having developed the condition \
by each age, not annual incidence. Probability must be non-decreasing across ages.
- Anchor to population base rates. A 30-year-old with no risk factors has a very \
low probability of most chronic disease; do not inflate it. Reserve high \
probabilities for genuinely high-risk profiles.
- Only report ages at or after the patient's current age where meaningful, but \
always return all five age buckets so the timeline renders. For ages already \
passed, report the probability of currently having the condition.
- Set `confidence` honestly per condition. If a key input is missing (no lipid \
panel for cardiovascular risk, no glucose for diabetes), that condition is `low` \
confidence and you must list what is missing in `missing_data`.
- Name the specific facts driving each risk in `drivers`. "Current smoker, \
15 pack-years" is useful; "lifestyle factors" is not.
- Never invent a lab value, diagnosis or family history that was not provided.
- Choose the conditions to report based on the profile. Typical categories: \
cardiovascular, metabolic, respiratory, oncologic, mental health, \
musculoskeletal. Report between 3 and 8 conditions.
- Map `level` from probability: <0.05 low, 0.05-0.15 moderate, 0.15-0.30 high, \
>0.30 very_high.

Write the `summary` and every `rationale` for the patient to read: plain \
language, direct, no hedging filler and no alarm. Do not tell the patient they \
"will" develop anything — these are probabilities.
"""


def _build_response_schema() -> dict:
    """JSON Schema for the engine's response.

    Written by hand rather than derived from the Pydantic models because the
    API's structured-output support rejects several keywords Pydantic emits
    (`minimum`/`maximum`, `$defs` recursion). Keep it in sync with
    `models/schemas.py` — `RiskAssessment` validation is what catches drift.
    """
    projection = {
        "type": "object",
        "properties": {
            "age": {"type": "integer", "enum": list(PROJECTION_AGES)},
            "probability": {
                "type": "number",
                "description": "Absolute probability from 0.0 to 1.0.",
            },
            "level": {
                "type": "string",
                "enum": ["low", "moderate", "high", "very_high"],
            },
        },
        "required": ["age", "probability", "level"],
        "additionalProperties": False,
    }

    condition = {
        "type": "object",
        "properties": {
            "condition": {"type": "string"},
            "category": {"type": "string"},
            "projections": {
                "type": "array",
                "items": projection,
                "description": "Exactly five entries, one per age 25/30/35/40/45.",
            },
            "drivers": {"type": "array", "items": {"type": "string"}},
            "protective_factors": {"type": "array", "items": {"type": "string"}},
            "rationale": {"type": "string"},
            "modifiable": {"type": "boolean"},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        },
        "required": [
            "condition",
            "category",
            "projections",
            "drivers",
            "protective_factors",
            "rationale",
            "modifiable",
            "confidence",
        ],
        "additionalProperties": False,
    }

    recommendation = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "detail": {"type": "string"},
            "priority": {
                "type": "string",
                "enum": ["urgent", "high", "medium", "low"],
            },
            "targets": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "detail", "priority", "targets"],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "conditions": {"type": "array", "items": condition},
            "recommendations": {"type": "array", "items": recommendation},
            "missing_data": {"type": "array", "items": {"type": "string"}},
            "extracted_profile": {
                "type": "object",
                "description": "Values you read from the report. Omit unknowns.",
                "properties": {
                    "age": {"type": "integer"},
                    "sex": {"type": "string", "enum": ["male", "female", "other"]},
                    "height_cm": {"type": "number"},
                    "weight_kg": {"type": "number"},
                    "systolic_bp": {"type": "integer"},
                    "diastolic_bp": {"type": "integer"},
                    "smoking": {
                        "type": "string",
                        "enum": ["never", "former", "current"],
                    },
                    "family_history": {"type": "array", "items": {"type": "string"}},
                    "existing_conditions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "labs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "value": {"type": "number"},
                                "unit": {"type": "string"},
                            },
                            "required": ["name", "value"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
        },
        "required": ["summary", "conditions", "recommendations", "missing_data"],
        "additionalProperties": False,
    }


RESPONSE_SCHEMA = _build_response_schema()


class LLMRiskEngine(RiskEngine):
    """Risk estimation via the Claude API."""

    name = "llm"

    def __init__(
        self,
        client: anthropic.AsyncAnthropic | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        # A bare constructor resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN or
        # an `ant auth login` profile, in that order.
        self._client = client or anthropic.AsyncAnthropic()
        self._model = model

    async def assess(
        self,
        profile: PatientProfile | None = None,
        report: ExtractedReport | None = None,
    ) -> RiskAssessment:
        if profile is None and (report is None or not report.has_content):
            raise RiskEngineError(
                "Provide either a patient profile or a readable report."
            )

        content = self._build_content(profile, report)

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                output_config={
                    "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}
                },
                messages=[{"role": "user", "content": content}],
            )
        except anthropic.APIStatusError as exc:
            logger.exception("Claude API returned %s", exc.status_code)
            raise RiskEngineError(
                f"The risk model is unavailable (HTTP {exc.status_code}). "
                "Please retry shortly."
            ) from exc
        except anthropic.APIConnectionError as exc:
            logger.exception("Could not reach the Claude API")
            raise RiskEngineError(
                "Could not reach the risk model. Check network connectivity."
            ) from exc
        except TypeError as exc:
            # The SDK raises a bare TypeError when it cannot resolve any
            # credential. This is the most likely first-run failure, so it gets
            # an actionable message rather than an opaque 500.
            if "authentication" in str(exc).lower():
                logger.error("No Anthropic credentials available")
                raise RiskEngineError(
                    "No API credentials configured. Set ANTHROPIC_API_KEY in "
                    "backend/.env (see .env.example) and restart the server."
                ) from exc
            raise

        # A refusal is a successful HTTP 200 with empty or partial content, so
        # this must be checked before touching `response.content`.
        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            category = getattr(detail, "category", None) if detail else None
            logger.warning("Model declined the request (category=%s)", category)
            raise RiskEngineError(
                "The model declined to analyse this input. If the report "
                "contains unusual content, try the manual form instead."
            )

        if response.stop_reason == "max_tokens":
            raise RiskEngineError(
                "The analysis was cut short before it finished. Try a shorter "
                "report, or reduce the number of conditions requested."
            )

        payload = self._first_text_block(response)
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            logger.error("Structured output was not valid JSON: %s", payload[:500])
            raise RiskEngineError(
                "The risk model returned a malformed response. Please retry."
            ) from exc

        return self._to_assessment(data, profile, report)

    @staticmethod
    def _first_text_block(response) -> str:
        for block in response.content:
            if block.type == "text":
                return block.text
        raise RiskEngineError("The risk model returned an empty response.")

    def _build_content(
        self, profile: PatientProfile | None, report: ExtractedReport | None
    ) -> list[dict]:
        """Assemble the user turn, including an image block when one was uploaded."""
        blocks: list[dict] = []

        if report and report.image_base64:
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": report.image_media_type,
                        "data": report.image_base64,
                    },
                }
            )

        parts: list[str] = []

        if profile is not None:
            parts.append("PATIENT PROFILE\n" + self._render_profile(profile))

        if report and report.text.strip():
            # Bounded so an unusually long report can't blow past the context
            # window or the token budget on a single request.
            parts.append("MEDICAL REPORT\n" + report.text[:60000])

        if report and report.image_base64:
            parts.append(
                "An image of the patient's medical report is attached above. "
                "Read every value you can see in it, including handwriting."
            )

        parts.append(
            "Produce the risk assessment for ages "
            + ", ".join(str(a) for a in PROJECTION_AGES)
            + ". Populate `extracted_profile` with the values you read."
        )

        blocks.append({"type": "text", "text": "\n\n".join(parts)})
        return blocks

    @staticmethod
    def _render_profile(profile: PatientProfile) -> str:
        """Render only the fields that are actually known.

        Emitting "Smoking: None" would read to the model as an assertion that the
        patient does not smoke, rather than as missing data.
        """
        lines: list[str] = [f"Age: {profile.age}"]

        simple: list[tuple[str, object]] = [
            ("Sex", profile.sex.value if profile.sex else None),
            ("Height (cm)", profile.height_cm),
            ("Weight (kg)", profile.weight_kg),
            ("BMI", profile.bmi),
            ("Smoking", profile.smoking.value if profile.smoking else None),
            ("Alcohol use", profile.alcohol.value if profile.alcohol else None),
            ("Activity level", profile.activity.value if profile.activity else None),
            (
                "Shift pattern",
                profile.shift_pattern.value if profile.shift_pattern else None,
            ),
            (
                "Stress level",
                profile.stress_level.value if profile.stress_level else None,
            ),
            ("Sleep (hours/night)", profile.sleep_hours),
        ]
        for label, value in simple:
            if value is not None:
                lines.append(f"{label}: {value}")

        if profile.systolic_bp and profile.diastolic_bp:
            lines.append(
                f"Blood pressure: {profile.systolic_bp}/{profile.diastolic_bp} mmHg"
            )

        for label, values in (
            ("Family history", profile.family_history),
            ("Existing conditions", profile.existing_conditions),
            ("Medications", profile.medications),
        ):
            if values:
                lines.append(f"{label}: {', '.join(values)}")

        if profile.labs:
            lines.append("Lab results:")
            for lab in profile.labs:
                unit = f" {lab.unit}" if lab.unit else ""
                flag = f" [{lab.flag}]" if lab.flag else ""
                lines.append(f"  - {lab.name}: {lab.value}{unit}{flag}")

        return "\n".join(lines)

    def _to_assessment(
        self,
        data: dict,
        profile: PatientProfile | None,
        report: ExtractedReport | None,
    ) -> RiskAssessment:
        resolved = self._resolve_profile(data, profile, report)

        try:
            assessment = RiskAssessment(
                profile=resolved,
                conditions=data.get("conditions", []),
                recommendations=data.get("recommendations", []),
                summary=data.get("summary", ""),
                missing_data=data.get("missing_data", []),
                engine=self.name,
                model=self._model,
            )
        except Exception as exc:
            # Structured outputs guarantee the schema, but not our extra
            # invariants (five ages, probability ordering).
            logger.error("Engine response failed validation: %s", exc)
            raise RiskEngineError(
                f"The risk model returned an inconsistent assessment: {exc}"
            ) from exc

        self._enforce_monotonic_risk(assessment)
        self._downgrade_confidence_if_sparse(assessment)
        return assessment

    def _resolve_profile(
        self,
        data: dict,
        profile: PatientProfile | None,
        report: ExtractedReport | None,
    ) -> PatientProfile:
        """Merge the model's extraction with the user-supplied profile.

        User-supplied values always win: a person who typed their own age is a
        better source than a model reading a scanned PDF.
        """
        extracted = data.get("extracted_profile") or {}

        if profile is not None:
            if not extracted:
                return profile
            merged = profile.model_dump()
            for key, value in extracted.items():
                if value in (None, [], "") or key not in merged:
                    continue
                if merged.get(key) in (None, [], ""):
                    merged[key] = value
            try:
                return PatientProfile(**merged)
            except Exception:
                return profile

        if not extracted.get("age"):
            raise RiskEngineError(
                "Could not determine the patient's age from the report. "
                "Enter it manually and try again."
            )

        try:
            return PatientProfile(
                **extracted,
                raw_report_text=(report.text[:20000] if report else None),
            )
        except Exception as exc:
            raise RiskEngineError(
                f"Could not build a patient profile from the report: {exc}"
            ) from exc

    @staticmethod
    def _enforce_monotonic_risk(assessment: RiskAssessment) -> None:
        """Clamp probabilities so risk never decreases with age.

        The prompt asks for this, but it is a hard invariant of cumulative
        incidence, so it is enforced rather than trusted — a dipping line would
        be visibly wrong in the chart.
        """
        for condition in assessment.conditions:
            running = 0.0
            for projection in condition.projections:
                if projection.probability < running:
                    projection.probability = running
                else:
                    running = projection.probability

    @staticmethod
    def _downgrade_confidence_if_sparse(assessment: RiskAssessment) -> None:
        """Cap confidence when the profile barely has any data in it.

        Guards against a confident-sounding assessment built from an age and
        nothing else.
        """
        if assessment.profile.known_field_count() >= 4:
            return
        for condition in assessment.conditions:
            if condition.confidence == Confidence.high:
                condition.confidence = Confidence.medium
        note = "Limited input data — estimates are broad population averages."
        if note not in assessment.missing_data:
            assessment.missing_data.insert(0, note)

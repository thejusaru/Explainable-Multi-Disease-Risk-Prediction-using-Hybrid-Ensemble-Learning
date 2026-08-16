"""Local LLM risk engine, backed by Ollama (Llama, Qwen, Mistral, …).

Same `RiskEngine` contract as the Claude engine, so the routes and the frontend
are unchanged. What differs is reliability, and the difference is large enough
to matter:

- **No enforced schema.** The Claude engine uses structured outputs, so the
  response shape is guaranteed. Ollama's `format: json` only guarantees *valid
  JSON* — not that it matches our schema. A 7B model regularly omits required
  fields, invents age buckets or emits probabilities as percentages.
- **No vision.** Image reports cannot be read by most local text models, so an
  image-only upload is rejected rather than silently analysed as if blank.

To compensate, this engine repairs what it can (§`_coerce_payload`) and retries
once with the validation error fed back before giving up.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.engines.base import RiskEngine, RiskEngineError
from app.engines.llm_engine import SYSTEM_PROMPT, LLMRiskEngine
from app.models.schemas import (
    PROJECTION_AGES,
    Confidence,
    PatientProfile,
    RiskAssessment,
)
from app.parsers.extract import ExtractedReport

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_LOCAL_MODEL = "qwen2.5:7b"

# Small models drift without a worked example of the exact shape, so the schema
# is restated concretely rather than described.
LOCAL_FORMAT_INSTRUCTIONS = f"""
Respond with a single JSON object and nothing else. No markdown fences, no
commentary before or after. The object must use exactly these keys and value
types — the placeholder text in angle brackets shows what goes in each field,
NOT a value to copy:

{{
  "summary": "<one paragraph in plain language>",
  "conditions": [
    {{
      "condition": "<name of the condition>",
      "category": "<cardiovascular | metabolic | respiratory | oncologic | mental_health | musculoskeletal>",
      "projections": [
        {{"age": 25, "probability": <decimal 0 to 1>, "level": "<low | moderate | high | very_high>"}},
        {{"age": 30, "probability": <decimal 0 to 1>, "level": "<...>"}},
        {{"age": 35, "probability": <decimal 0 to 1>, "level": "<...>"}},
        {{"age": 40, "probability": <decimal 0 to 1>, "level": "<...>"}},
        {{"age": 45, "probability": <decimal 0 to 1>, "level": "<...>"}}
      ],
      "drivers": ["<specific fact from this patient's profile>"],
      "protective_factors": ["<specific protective fact, or empty list>"],
      "rationale": "<one or two sentences specific to this condition>",
      "modifiable": <true or false>,
      "confidence": "<low | medium | high>"
    }}
  ],
  "recommendations": [
    {{"title": "<short action>", "detail": "<why and how>",
      "priority": "<urgent | high | medium | low>",
      "targets": ["<condition name this reduces risk for>"]}}
  ],
  "missing_data": ["<data that would improve the estimate>"],
  "extracted_profile": {{"age": <patient's age as an integer>}}
}}

Hard requirements:
- `projections` must contain exactly {len(PROJECTION_AGES)} entries, for ages
  {", ".join(str(a) for a in PROJECTION_AGES)} — in that order, no others.
- `probability` is a decimal between 0 and 1. Write 0.15, never 15.
- `level` is exactly one of: low, moderate, high, very_high.
- `confidence` is exactly one of: low, medium, high.
- `priority` is exactly one of: urgent, high, medium, low.
- Report between 3 and 6 conditions.

CRITICAL — each condition must have its OWN distinct probabilities. Different
diseases have very different base rates and respond to different risk factors,
so two conditions must not share the same five numbers. Work out each condition
separately from the specific factors that drive it:
- Smoking drives lung cancer and coronary disease, barely affects diabetes.
- Obesity and high HbA1c drive type 2 diabetes far more than they drive cancer.
- Hypertension is common: its probabilities are typically much higher than
  those for any specific cancer at the same age.
If you find yourself writing the same number twice for different conditions,
stop and reconsider that condition's actual base rate.
"""


class LocalRiskEngine(RiskEngine):
    """Risk estimation via a locally-hosted model served by Ollama."""

    name = "local"

    def __init__(
        self,
        model: str = DEFAULT_LOCAL_MODEL,
        host: str = DEFAULT_OLLAMA_HOST,
        timeout: float = 300.0,
    ) -> None:
        self._model = model
        self._host = host.rstrip("/")
        self._timeout = timeout

    async def assess(
        self,
        profile: PatientProfile | None = None,
        report: ExtractedReport | None = None,
    ) -> RiskAssessment:
        if profile is None and (report is None or not report.has_content):
            raise RiskEngineError(
                "Provide either a patient profile or a readable report."
            )

        # Fail loudly rather than analysing an image the model cannot see.
        if report and report.image_base64 and not report.text.strip():
            raise RiskEngineError(
                f"The local model '{self._model}' cannot read images. Switch to "
                "the Claude engine for photo uploads, or enter the values "
                "manually."
            )

        prompt = self._build_prompt(profile, report)
        system = SYSTEM_PROMPT + "\n" + LOCAL_FORMAT_INSTRUCTIONS

        payload = await self._generate(system, prompt)

        try:
            return self._to_assessment(payload, profile, report)
        except RiskEngineError as first_error:
            # One retry with the specific failure fed back. Small models often
            # fix a named structural error even when they cannot get it right
            # cold.
            logger.warning("Local model output invalid, retrying: %s", first_error)
            repair = (
                f"{prompt}\n\nYour previous response was rejected: {first_error}\n"
                "Return corrected JSON matching the required shape exactly."
            )
            retry_payload = await self._generate(system, repair)
            try:
                return self._to_assessment(retry_payload, profile, report)
            except RiskEngineError as second_error:
                raise RiskEngineError(
                    f"The local model '{self._model}' could not produce a valid "
                    f"assessment after two attempts ({second_error}). Smaller "
                    "models struggle with strict output formats — try a larger "
                    "one, or switch to the Claude engine."
                ) from second_error

    async def _generate(self, system: str, prompt: str) -> dict:
        """Call Ollama and return the parsed JSON object."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._host}/api/generate",
                    json={
                        "model": self._model,
                        "system": system,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        # Low temperature for the most consistent structure a
                        # local model can manage. Still not reproducible.
                        "options": {"temperature": 0.2, "num_ctx": 8192},
                    },
                )
        except httpx.ConnectError as exc:
            raise RiskEngineError(
                f"Could not reach Ollama at {self._host}. Start it with "
                "'ollama serve', or switch to the Claude engine."
            ) from exc
        except httpx.TimeoutException as exc:
            raise RiskEngineError(
                f"The local model '{self._model}' timed out after "
                f"{self._timeout:.0f}s. Local inference is slow on CPU — try a "
                "smaller model, or switch to the Claude engine."
            ) from exc

        if response.status_code == 404:
            raise RiskEngineError(
                f"Model '{self._model}' is not installed in Ollama. "
                f"Run: ollama pull {self._model}"
            )
        if response.status_code >= 400:
            raise RiskEngineError(
                f"Ollama returned HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )

        body = response.json()
        raw = (body.get("response") or "").strip()
        if not raw:
            raise RiskEngineError("The local model returned an empty response.")

        return self._parse_json(raw)

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """Parse the model's output, tolerating the usual local-model noise."""
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Strip markdown fences, which appear despite format:json.
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
        if fenced:
            try:
                parsed = json.loads(fenced.group(1))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        # Last resort: the outermost {...} span.
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            try:
                parsed = json.loads(raw[start : end + 1])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        logger.error("Unparseable local model output: %s", raw[:400])
        raise RiskEngineError(
            "The local model did not return valid JSON. Smaller models often "
            "struggle with this — try a larger model or the Claude engine."
        )

    def _build_prompt(
        self, profile: PatientProfile | None, report: ExtractedReport | None
    ) -> str:
        parts: list[str] = []
        if profile is not None:
            # Reuse the Claude engine's renderer so both paths describe a
            # patient identically — one prompt-format bug, not two.
            parts.append(
                "PATIENT PROFILE\n" + LLMRiskEngine._render_profile(profile)
            )
        if report and report.text.strip():
            # Tighter cap than the Claude path: 7B context windows are small.
            parts.append("MEDICAL REPORT\n" + report.text[:12000])
        parts.append(
            "Produce the risk assessment for ages "
            + ", ".join(str(a) for a in PROJECTION_AGES)
            + " as a single JSON object."
        )
        return "\n\n".join(parts)

    def _to_assessment(
        self,
        payload: dict,
        profile: PatientProfile | None,
        report: ExtractedReport | None,
    ) -> RiskAssessment:
        data = self._coerce_payload(payload)

        # Profile resolution, monotonic clamping and confidence capping are
        # identical across engines, so they are reused rather than duplicated.
        helper = LLMRiskEngine.__new__(LLMRiskEngine)
        helper._model = self._model
        resolved = LLMRiskEngine._resolve_profile(helper, data, profile, report)

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
            raise RiskEngineError(f"invalid assessment structure: {exc}") from exc

        LLMRiskEngine._enforce_monotonic_risk(assessment)
        LLMRiskEngine._downgrade_confidence_if_sparse(assessment)

        # A local model's self-reported confidence is not trustworthy at this
        # size; cap it so the UI never overstates what a 7B model produced.
        for condition in assessment.conditions:
            if condition.confidence == Confidence.high:
                condition.confidence = Confidence.medium

        self._flag_duplicate_curves(assessment)
        return assessment

    @staticmethod
    def _flag_duplicate_curves(assessment: RiskAssessment) -> None:
        """Warn when conditions share an identical probability curve.

        Observed with qwen2.5:7b: the model reproduces one curve across every
        condition instead of reasoning per disease. The numbers are then close
        to meaningless, but nothing about the response is structurally invalid,
        so it would otherwise render as a confident-looking chart of parallel
        lines. Surfaced rather than silently corrected — there is no honest way
        to invent the right per-condition values here.
        """
        if len(assessment.conditions) < 2:
            return

        seen: dict[tuple[float, ...], list[str]] = {}
        for condition in assessment.conditions:
            key = tuple(p.probability for p in condition.projections)
            seen.setdefault(key, []).append(condition.condition)

        duplicated = [names for names in seen.values() if len(names) > 1]
        if not duplicated:
            return

        largest = max(duplicated, key=len)
        logger.warning(
            "Local model produced identical curves for: %s", ", ".join(largest)
        )
        assessment.missing_data.insert(
            0,
            f"The local model gave identical probabilities to {len(largest)} "
            f"conditions ({', '.join(largest)}), which means it did not "
            "estimate them separately. Treat these numbers as unreliable and "
            "re-run with the Claude engine or a larger local model.",
        )

    @staticmethod
    def _coerce_payload(payload: dict) -> dict:
        """Repair the structural mistakes small models make predictably.

        Only unambiguous fixes are applied — anything requiring a guess about
        clinical meaning is left to fail validation instead.
        """
        data = dict(payload)

        conditions = data.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            raise RiskEngineError("response contained no conditions")

        repaired: list[dict] = []
        for raw in conditions:
            if not isinstance(raw, dict):
                continue

            condition = dict(raw)
            condition.setdefault("category", "general")
            condition.setdefault("drivers", [])
            condition.setdefault("protective_factors", [])
            condition.setdefault("rationale", "")
            condition.setdefault("modifiable", True)
            condition.setdefault("confidence", "low")

            name = condition.get("condition")
            if not isinstance(name, str) or not name.strip():
                continue

            by_age: dict[int, dict] = {}
            for entry in condition.get("projections") or []:
                if not isinstance(entry, dict):
                    continue
                try:
                    age = int(entry.get("age"))
                    probability = float(entry.get("probability"))
                except (TypeError, ValueError):
                    continue
                if age not in PROJECTION_AGES:
                    continue
                # Percentages instead of proportions are the single most common
                # slip; 0-1 is unambiguous so the rescale is safe.
                if probability > 1.0:
                    probability = probability / 100.0
                probability = max(0.0, min(1.0, probability))
                by_age[age] = {
                    "age": age,
                    "probability": probability,
                    "level": _normalise_level(entry.get("level"), probability),
                }

            if not by_age:
                continue

            # Fill any missing bucket by carrying the last known value forward.
            # Interpolating would invent a trend the model never stated.
            filled: list[dict] = []
            last = 0.0
            for age in PROJECTION_AGES:
                if age in by_age:
                    last = by_age[age]["probability"]
                    filled.append(by_age[age])
                else:
                    filled.append(
                        {
                            "age": age,
                            "probability": last,
                            "level": _normalise_level(None, last),
                        }
                    )
            condition["projections"] = filled

            confidence = str(condition.get("confidence", "low")).lower()
            condition["confidence"] = (
                confidence if confidence in {"low", "medium", "high"} else "low"
            )
            repaired.append(condition)

        if not repaired:
            raise RiskEngineError("no usable conditions after repair")

        data["conditions"] = repaired

        recommendations: list[dict] = []
        for raw in data.get("recommendations") or []:
            if not isinstance(raw, dict) or not raw.get("title"):
                continue
            rec = dict(raw)
            rec.setdefault("detail", "")
            rec.setdefault("targets", [])
            priority = str(rec.get("priority", "medium")).lower()
            rec["priority"] = (
                priority
                if priority in {"urgent", "high", "medium", "low"}
                else "medium"
            )
            recommendations.append(rec)
        data["recommendations"] = recommendations

        if not isinstance(data.get("summary"), str):
            data["summary"] = ""
        if not isinstance(data.get("missing_data"), list):
            data["missing_data"] = []

        return data


def _normalise_level(value: Any, probability: float) -> str:
    """Return a valid risk level, deriving one from probability if needed."""
    allowed = {"low", "moderate", "high", "very_high"}
    if isinstance(value, str):
        candidate = value.strip().lower().replace(" ", "_").replace("-", "_")
        if candidate in allowed:
            return candidate
        # "very high risk" and similar prose variants.
        if "very" in candidate and "high" in candidate:
            return "very_high"

    # Thresholds mirror the ones in the shared system prompt.
    if probability < 0.05:
        return "low"
    if probability < 0.15:
        return "moderate"
    if probability < 0.30:
        return "high"
    return "very_high"

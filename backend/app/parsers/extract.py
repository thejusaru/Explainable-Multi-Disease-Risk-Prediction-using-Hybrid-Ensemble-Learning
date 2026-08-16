"""Turn an uploaded report into text the risk engine can read.

Four input paths are supported. PDFs and images both end up as text (or as an
image block passed straight to the vision model); FHIR bundles are mapped
structurally; the manual form skips this module entirely.

Optional dependencies are imported lazily so the service still boots — and
still serves the form and FHIR paths — when `pypdf` or `Pillow` is absent.
"""

from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass, field

from app.models.schemas import (
    LabResult,
    PatientProfile,
    Sex,
    SmokingStatus,
)

# Anthropic's vision API accepts these; anything else we refuse rather than
# mislabel the media_type and get an opaque 400 back.
SUPPORTED_IMAGE_TYPES = {
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/png": "image/png",
    "image/gif": "image/gif",
    "image/webp": "image/webp",
}

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class UnsupportedFileError(ValueError):
    """Raised when we cannot turn the upload into anything the engine can use."""


@dataclass
class ExtractedReport:
    """The normalised result of reading one upload.

    Exactly one of `text` or `image` carries the payload. When `image` is set the
    engine forwards it to the vision model instead of doing OCR locally, which
    avoids shipping a Tesseract dependency for a POC.
    """

    text: str = ""
    image_base64: str | None = None
    image_media_type: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def has_content(self) -> bool:
        return bool(self.text.strip() or self.image_base64)


def extract_from_upload(
    filename: str, content_type: str | None, data: bytes
) -> ExtractedReport:
    """Dispatch an upload to the right reader based on its type."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise UnsupportedFileError(
            f"File is {len(data) // (1024 * 1024)}MB; the limit is "
            f"{MAX_UPLOAD_BYTES // (1024 * 1024)}MB."
        )
    if not data:
        raise UnsupportedFileError("File is empty.")

    lowered = (filename or "").lower()
    ctype = (content_type or "").lower().split(";")[0].strip()

    if ctype == "application/pdf" or lowered.endswith(".pdf"):
        return _extract_pdf(data)
    if ctype in SUPPORTED_IMAGE_TYPES or lowered.endswith(
        (".png", ".jpg", ".jpeg", ".gif", ".webp")
    ):
        return _extract_image(data, ctype, lowered)
    if ctype == "application/json" or lowered.endswith(".json"):
        return _extract_fhir(data)
    if ctype.startswith("text/") or lowered.endswith((".txt", ".md")):
        return ExtractedReport(
            text=data.decode("utf-8", errors="replace"),
            notes=["Read as plain text."],
        )

    raise UnsupportedFileError(
        f"Unsupported file type '{content_type or filename}'. "
        "Upload a PDF, an image (PNG/JPEG/WebP), a FHIR JSON bundle, or plain text."
    )


def _extract_pdf(data: bytes) -> ExtractedReport:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on install
        raise UnsupportedFileError(
            "PDF support requires the 'pypdf' package. Install it, or paste the "
            "report text into the manual form."
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise UnsupportedFileError(f"Could not read the PDF: {exc}") from exc

    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            # One unreadable page shouldn't lose the other twenty.
            pages.append("")

    text = "\n\n".join(p for p in pages if p.strip())
    notes = [f"Extracted text from {len(reader.pages)} PDF page(s)."]

    if not text.strip():
        # A scanned PDF has pages but no text layer. Say so explicitly — this is
        # the single most common confusing failure with lab report uploads.
        raise UnsupportedFileError(
            "This PDF has no extractable text layer — it is most likely a scan. "
            "Upload the report as an image instead so it can be read visually."
        )

    return ExtractedReport(text=text, notes=notes)


def _extract_image(data: bytes, ctype: str, filename: str) -> ExtractedReport:
    media_type = SUPPORTED_IMAGE_TYPES.get(ctype)
    if media_type is None:
        for suffix, mapped in (
            (".png", "image/png"),
            (".jpg", "image/jpeg"),
            (".jpeg", "image/jpeg"),
            (".gif", "image/gif"),
            (".webp", "image/webp"),
        ):
            if filename.endswith(suffix):
                media_type = mapped
                break
    if media_type is None:
        raise UnsupportedFileError(f"Unsupported image type '{ctype}'.")

    return ExtractedReport(
        image_base64=base64.standard_b64encode(data).decode("ascii"),
        image_media_type=media_type,
        notes=["Image forwarded to the vision model for reading."],
    )


def _extract_fhir(data: bytes) -> ExtractedReport:
    """Flatten a FHIR bundle into readable text.

    This is not a conformant FHIR client — it walks the resource types that
    carry the values we care about (Patient, Observation, Condition,
    MedicationRequest) and renders them as lines. Anything else is ignored.
    """
    try:
        payload = json.loads(data.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise UnsupportedFileError(f"Not valid JSON: {exc}") from exc

    entries = payload.get("entry") or []
    if not isinstance(entries, list):
        entries = []

    # A bare resource (not wrapped in a Bundle) is also worth accepting.
    if not entries and payload.get("resourceType"):
        entries = [{"resource": payload}]

    lines: list[str] = []
    seen_types: set[str] = set()

    for entry in entries:
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(resource, dict):
            continue
        rtype = resource.get("resourceType", "")
        seen_types.add(rtype)

        if rtype == "Patient":
            if gender := resource.get("gender"):
                lines.append(f"Sex: {gender}")
            if birth := resource.get("birthDate"):
                lines.append(f"Date of birth: {birth}")
        elif rtype == "Observation":
            label = _fhir_label(resource.get("code"))
            value = _fhir_value(resource)
            if label and value:
                lines.append(f"{label}: {value}")
            for component in resource.get("component", []) or []:
                clabel = _fhir_label(component.get("code"))
                cvalue = _fhir_value(component)
                if clabel and cvalue:
                    lines.append(f"{clabel}: {cvalue}")
        elif rtype == "Condition":
            if label := _fhir_label(resource.get("code")):
                lines.append(f"Diagnosed condition: {label}")
        elif rtype == "MedicationRequest":
            label = _fhir_label(resource.get("medicationCodeableConcept"))
            if label:
                lines.append(f"Medication: {label}")

    if not lines:
        raise UnsupportedFileError(
            "No usable clinical data found in that JSON. Expected a FHIR Bundle "
            "containing Patient, Observation, Condition or MedicationRequest "
            "resources."
        )

    note = f"Parsed FHIR resources: {', '.join(sorted(t for t in seen_types if t))}."
    return ExtractedReport(text="\n".join(lines), notes=[note])


def _fhir_label(code: object) -> str | None:
    """Pull a human label out of a FHIR CodeableConcept."""
    if not isinstance(code, dict):
        return None
    if text := code.get("text"):
        return str(text)
    for coding in code.get("coding", []) or []:
        if isinstance(coding, dict) and (display := coding.get("display")):
            return str(display)
    return None


def _fhir_value(resource: dict) -> str | None:
    """Render whichever value[x] variant a FHIR element happens to use."""
    quantity = resource.get("valueQuantity")
    if isinstance(quantity, dict) and quantity.get("value") is not None:
        unit = quantity.get("unit") or quantity.get("code") or ""
        return f"{quantity['value']} {unit}".strip()
    if (value := resource.get("valueString")) is not None:
        return str(value)
    if (value := resource.get("valueBoolean")) is not None:
        return str(value)
    if label := _fhir_label(resource.get("valueCodeableConcept")):
        return label
    return None


# --- Lightweight pre-extraction -------------------------------------------
#
# The LLM does the real extraction. These regexes only pre-fill obvious values
# so that (a) the UI can show something immediately and (b) an outright wrong
# LLM reading of a plainly-stated number is easier to spot.

_AGE_RE = re.compile(r"\b(?:age|aged)\s*[:\-]?\s*(\d{1,3})\b", re.I)
_BP_RE = re.compile(r"\b(\d{2,3})\s*/\s*(\d{2,3})\s*(?:mm\s*hg)?\b", re.I)
_HEIGHT_RE = re.compile(r"\bheight\s*[:\-]?\s*(\d{2,3}(?:\.\d+)?)\s*cm\b", re.I)
_WEIGHT_RE = re.compile(r"\bweight\s*[:\-]?\s*(\d{2,3}(?:\.\d+)?)\s*kg\b", re.I)

_LAB_PATTERNS = {
    "Total cholesterol": re.compile(
        r"\btotal\s+cholesterol\s*[:\-]?\s*(\d{2,3}(?:\.\d+)?)", re.I
    ),
    "HDL cholesterol": re.compile(r"\bhdl\b[^\d\n]{0,20}(\d{1,3}(?:\.\d+)?)", re.I),
    "LDL cholesterol": re.compile(r"\bldl\b[^\d\n]{0,20}(\d{1,3}(?:\.\d+)?)", re.I),
    "Triglycerides": re.compile(
        r"\btriglycerides?\s*[:\-]?\s*(\d{2,4}(?:\.\d+)?)", re.I
    ),
    "HbA1c": re.compile(r"\bhba1c\b[^\d\n]{0,20}(\d{1,2}(?:\.\d+)?)", re.I),
    "Fasting glucose": re.compile(
        r"\b(?:fasting\s+)?glucose\s*[:\-]?\s*(\d{2,3}(?:\.\d+)?)", re.I
    ),
}


def prefill_profile_from_text(text: str) -> PatientProfile | None:
    """Best-effort structured read of a report. Returns None without an age.

    Age is required by `PatientProfile` and is the anchor for the whole
    projection, so a report we can't find an age in isn't worth pre-filling.
    """
    if not text or not text.strip():
        return None

    age_match = _AGE_RE.search(text)
    if not age_match:
        return None

    age = int(age_match.group(1))
    if not 0 <= age <= 120:
        return None

    profile_data: dict[str, object] = {"age": age, "raw_report_text": text[:20000]}

    if bp := _BP_RE.search(text):
        systolic, diastolic = int(bp.group(1)), int(bp.group(2))
        # Reject transposed or nonsensical readings rather than feeding them on.
        if 50 <= systolic <= 300 and 30 <= diastolic <= 200 and systolic > diastolic:
            profile_data["systolic_bp"] = systolic
            profile_data["diastolic_bp"] = diastolic

    if height := _HEIGHT_RE.search(text):
        profile_data["height_cm"] = float(height.group(1))
    if weight := _WEIGHT_RE.search(text):
        profile_data["weight_kg"] = float(weight.group(1))

    lowered = text.lower()
    if re.search(r"\b(?:non[- ]?smoker|never smoked)\b", lowered):
        profile_data["smoking"] = SmokingStatus.never
    elif re.search(r"\b(?:ex[- ]?smoker|former smoker|quit smoking)\b", lowered):
        profile_data["smoking"] = SmokingStatus.former
    elif re.search(r"\b(?:smoker|smokes|smoking)\b", lowered):
        profile_data["smoking"] = SmokingStatus.current

    if re.search(r"\b(?:female|woman)\b", lowered):
        profile_data["sex"] = Sex.female
    elif re.search(r"\b(?:male|man)\b", lowered):
        profile_data["sex"] = Sex.male

    labs: list[LabResult] = []
    for name, pattern in _LAB_PATTERNS.items():
        if match := pattern.search(text):
            try:
                labs.append(LabResult(name=name, value=float(match.group(1))))
            except ValueError:
                continue
    if labs:
        profile_data["labs"] = labs

    try:
        return PatientProfile(**profile_data)
    except Exception:
        # Pre-fill is a convenience; never let it break the request.
        return None

"""Extraction and analysis endpoints.

The flow is deliberately two-step:

    POST /api/extract          read the report, return what was found
    (user reviews / corrects)
    POST /api/analyze/profile  run the risk assessment on confirmed values

Reading and estimating are separated so a misparsed value gets caught by a
human before it reaches the risk model. `POST /api/analyze/report` remains for
callers that want the old one-shot behaviour.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.config import EngineKind
from app.dependencies import resolve_engine
from app.engines.base import RiskEngineError
from app.models.schemas import (
    AnalyzeResponse,
    ExtractResponse,
    PatientProfile,
)
from app.parsers.extract import (
    ExtractedReport,
    UnsupportedFileError,
    extract_from_upload,
    prefill_profile_from_text,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["analysis"])

# Labels for the fields we surface as "found", in the order a clinician reads
# them. Keys are PatientProfile attribute names.
_FIELD_LABELS: list[tuple[str, str]] = [
    ("age", "Age"),
    ("sex", "Sex"),
    ("height_cm", "Height"),
    ("weight_kg", "Weight"),
    ("systolic_bp", "Blood pressure"),
    ("smoking", "Smoking status"),
    ("alcohol", "Alcohol use"),
    ("activity", "Activity level"),
    ("shift_pattern", "Work pattern"),
    ("stress_level", "Stress level"),
    ("sleep_hours", "Sleep"),
]


def _describe_found_fields(profile: PatientProfile) -> list[str]:
    """Name what was actually read, so the UI can say more than 'done'."""
    found: list[str] = []
    for attribute, label in _FIELD_LABELS:
        if getattr(profile, attribute, None) is not None:
            found.append(label)
    if profile.labs:
        found.append(f"{len(profile.labs)} lab result(s)")
    if profile.family_history:
        found.append("Family history")
    if profile.existing_conditions:
        found.append("Existing conditions")
    return found


@router.post("/extract", response_model=ExtractResponse)
async def extract_report(file: UploadFile = File(...)) -> ExtractResponse:
    """Read an uploaded report and return the values found, without analysing."""
    data = await file.read()

    try:
        report = extract_from_upload(file.filename or "", file.content_type, data)
    except UnsupportedFileError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    notes = list(report.notes)

    # Images have no text to regex over — the vision model reads them during
    # analysis, so there is nothing to pre-fill here.
    if report.image_base64 and not report.text.strip():
        notes.append(
            "Values will be read from the image during analysis. "
            "Fill in anything you already know to improve the estimate."
        )
        return ExtractResponse(
            profile=None,
            fields_found=[],
            notes=notes,
            requires_manual_entry=True,
            image_base64=report.image_base64,
            image_media_type=report.image_media_type,
        )

    profile = prefill_profile_from_text(report.text) if report.text else None

    if profile is None:
        notes.append(
            "Could not read a patient age from this report. "
            "Enter the details manually below."
        )
        return ExtractResponse(
            profile=None,
            fields_found=[],
            notes=notes,
            requires_manual_entry=True,
            report_text=report.text[:20000] if report.text else None,
        )

    found = _describe_found_fields(profile)
    notes.append(f"Read {len(found)} field(s) from the report.")

    return ExtractResponse(
        profile=profile,
        fields_found=found,
        notes=notes,
        requires_manual_entry=False,
        report_text=report.text[:20000],
    )


class ProfileAnalysisRequest(BaseModel):
    """A confirmed profile, optionally with the report text it came from."""

    profile: PatientProfile
    engine: EngineKind | None = None
    model: str | None = None

    report_text: str | None = Field(
        default=None,
        description="Report text from a prior /api/extract call, to avoid re-upload.",
    )
    image_base64: str | None = None
    image_media_type: str | None = None


@router.post("/analyze/profile", response_model=AnalyzeResponse)
async def analyze_profile(request: ProfileAnalysisRequest) -> AnalyzeResponse:
    """Assess risk from a confirmed patient profile."""
    engine = resolve_engine(request.engine, request.model)

    # Carry the original report through when the client has it, so the model
    # sees free-text context (clinician notes, family history) that the
    # structured form cannot capture.
    report: ExtractedReport | None = None
    if request.report_text or request.image_base64:
        report = ExtractedReport(
            text=request.report_text or "",
            image_base64=request.image_base64,
            image_media_type=request.image_media_type,
        )

    try:
        assessment = await engine.assess(profile=request.profile, report=report)
    except RiskEngineError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return AnalyzeResponse(assessment=assessment, extraction_notes=[])


@router.post("/analyze/report", response_model=AnalyzeResponse)
async def analyze_report(
    file: UploadFile = File(...),
    profile_json: str | None = Form(default=None),
    engine: EngineKind | None = Query(default=None),
    model: str | None = Query(default=None),
) -> AnalyzeResponse:
    """One-shot: read a report and assess it in a single call.

    Kept for API clients and scripts. The UI uses /extract then /analyze/profile
    so the user can correct values first.
    """
    data = await file.read()

    try:
        report = extract_from_upload(file.filename or "", file.content_type, data)
    except UnsupportedFileError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    notes = list(report.notes)

    profile: PatientProfile | None = None
    if profile_json:
        try:
            profile = PatientProfile(**json.loads(profile_json))
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=422, detail=f"profile_json is not valid JSON: {exc}"
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail=f"profile_json is not a valid profile: {exc}"
            ) from exc

    if profile is None and report.text:
        if prefilled := prefill_profile_from_text(report.text):
            profile = prefilled
            notes.append(
                f"Pre-read age {prefilled.age} and "
                f"{prefilled.known_field_count()} other field(s) from the report text."
            )

    selected = resolve_engine(engine, model)

    try:
        assessment = await selected.assess(profile=profile, report=report)
    except RiskEngineError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return AnalyzeResponse(assessment=assessment, extraction_notes=notes)

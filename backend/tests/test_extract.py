"""Tests for the ingestion layer."""

from __future__ import annotations

import json

import pytest

from app.models.schemas import SmokingStatus
from app.parsers.extract import (
    UnsupportedFileError,
    extract_from_upload,
    prefill_profile_from_text,
)

SAMPLE_REPORT = """
ANNUAL HEALTH SCREENING

Patient: male, age 34
Height: 178 cm
Weight: 92 kg
Blood pressure: 148/94 mmHg

Social history: patient is a current smoker, approximately 15 cigarettes daily.
Works rotating night shifts.

LABORATORY RESULTS
Total cholesterol: 245 mg/dL
HDL: 38 mg/dL
LDL: 165 mg/dL
Triglycerides: 210 mg/dL
HbA1c: 6.1 %
Fasting glucose: 112 mg/dL
"""


def test_prefill_reads_core_values():
    profile = prefill_profile_from_text(SAMPLE_REPORT)
    assert profile is not None
    assert profile.age == 34
    assert profile.height_cm == 178
    assert profile.weight_kg == 92
    assert profile.systolic_bp == 148
    assert profile.diastolic_bp == 94
    assert profile.smoking == SmokingStatus.current


def test_prefill_reads_labs():
    profile = prefill_profile_from_text(SAMPLE_REPORT)
    assert profile is not None
    labs = {lab.name: lab.value for lab in profile.labs}
    assert labs["Total cholesterol"] == 245
    assert labs["HbA1c"] == 6.1


def test_prefill_returns_none_without_an_age():
    assert prefill_profile_from_text("Blood pressure: 120/80") is None
    assert prefill_profile_from_text("") is None


def test_prefill_distinguishes_non_smoker():
    profile = prefill_profile_from_text("Age: 40. Patient is a non-smoker.")
    assert profile is not None
    assert profile.smoking == SmokingStatus.never


def test_prefill_ignores_transposed_blood_pressure():
    # 80/120 is diastolic-over-systolic; better to drop it than pass it on.
    profile = prefill_profile_from_text("Age: 40\nBlood pressure: 80/120 mmHg")
    assert profile is not None
    assert profile.systolic_bp is None


def test_plain_text_upload_is_read():
    report = extract_from_upload("notes.txt", "text/plain", SAMPLE_REPORT.encode())
    assert "ANNUAL HEALTH SCREENING" in report.text
    assert report.has_content


def test_image_upload_is_base64_encoded_for_vision():
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    report = extract_from_upload("scan.png", "image/png", png_bytes)
    assert report.image_base64
    assert report.image_media_type == "image/png"
    assert not report.text


def test_fhir_bundle_is_flattened():
    bundle = {
        "resourceType": "Bundle",
        "entry": [
            {"resource": {"resourceType": "Patient", "gender": "female",
                          "birthDate": "1990-04-02"}},
            {
                "resource": {
                    "resourceType": "Observation",
                    "code": {"text": "Systolic blood pressure"},
                    "valueQuantity": {"value": 142, "unit": "mmHg"},
                }
            },
            {
                "resource": {
                    "resourceType": "Condition",
                    "code": {"coding": [{"display": "Type 2 diabetes mellitus"}]},
                }
            },
        ],
    }
    report = extract_from_upload(
        "bundle.json", "application/json", json.dumps(bundle).encode()
    )
    assert "Sex: female" in report.text
    assert "Systolic blood pressure: 142 mmHg" in report.text
    assert "Type 2 diabetes mellitus" in report.text


def test_fhir_accepts_a_bare_resource():
    resource = {
        "resourceType": "Observation",
        "code": {"text": "HbA1c"},
        "valueQuantity": {"value": 6.4, "unit": "%"},
    }
    report = extract_from_upload(
        "obs.json", "application/json", json.dumps(resource).encode()
    )
    assert "HbA1c: 6.4 %" in report.text


def test_json_without_clinical_data_is_rejected():
    with pytest.raises(UnsupportedFileError, match="No usable clinical data"):
        extract_from_upload("x.json", "application/json", b'{"hello": "world"}')


def test_empty_upload_is_rejected():
    with pytest.raises(UnsupportedFileError, match="empty"):
        extract_from_upload("empty.txt", "text/plain", b"")


def test_unknown_type_is_rejected():
    with pytest.raises(UnsupportedFileError, match="Unsupported file type"):
        extract_from_upload("archive.zip", "application/zip", b"PK\x03\x04data")


def test_oversized_upload_is_rejected():
    with pytest.raises(UnsupportedFileError, match="limit is"):
        extract_from_upload("big.txt", "text/plain", b"x" * (26 * 1024 * 1024))

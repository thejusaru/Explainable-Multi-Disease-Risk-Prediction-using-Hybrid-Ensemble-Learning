"""Tests for POST /api/extract.

This endpoint exists so parsed values reach the user for review before they
reach the risk model. These cover the contract the frontend form depends on:
which fields come back, and what happens when nothing can be parsed.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

REPORT = """
ANNUAL SCREENING
Patient: male, age 34
Height: 178 cm
Weight: 92 kg
Blood pressure: 148/94 mmHg
Social history: current smoker.
Total cholesterol: 245 mg/dL
HbA1c: 6.1 %
"""


def _post(filename: str, content_type: str, data: bytes):
    return client.post(
        "/api/extract", files={"file": (filename, data, content_type)}
    )


def test_extracts_profile_from_text_report():
    response = _post("report.txt", "text/plain", REPORT.encode())
    assert response.status_code == 200

    body = response.json()
    profile = body["profile"]

    assert profile is not None
    assert profile["age"] == 34
    assert profile["systolic_bp"] == 148
    assert profile["diastolic_bp"] == 94
    assert profile["smoking"] == "current"
    assert profile["height_cm"] == 178
    assert body["requires_manual_entry"] is False


def test_reports_which_fields_were_found():
    """The UI lists these as chips, so the labels are part of the contract."""
    body = _post("report.txt", "text/plain", REPORT.encode()).json()
    found = body["fields_found"]

    assert "Age" in found
    assert "Blood pressure" in found
    assert "Smoking status" in found
    assert any("lab result" in f for f in found)


def test_report_text_is_echoed_for_reuse():
    """Analysis reuses this instead of asking the user to upload again."""
    body = _post("report.txt", "text/plain", REPORT.encode()).json()
    assert body["report_text"]
    assert "ANNUAL SCREENING" in body["report_text"]


def test_unparseable_report_requests_manual_entry():
    body = _post(
        "notes.txt", "text/plain", b"Patient seen today. Follow up in 6 months."
    ).json()

    assert body["profile"] is None
    assert body["requires_manual_entry"] is True
    assert body["fields_found"] == []
    assert any("manually" in note for note in body["notes"])


def test_image_defers_reading_to_analysis():
    """No local OCR — the vision model reads it during the analysis call."""
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    body = _post("scan.png", "image/png", png).json()

    assert body["profile"] is None
    assert body["requires_manual_entry"] is True
    assert body["image_base64"]
    assert body["image_media_type"] == "image/png"


def test_fhir_bundle_is_accepted():
    bundle = {
        "resourceType": "Bundle",
        "entry": [
            {"resource": {"resourceType": "Patient", "gender": "male"}},
            {
                "resource": {
                    "resourceType": "Observation",
                    "code": {"text": "Systolic blood pressure"},
                    "valueQuantity": {"value": 152, "unit": "mmHg"},
                }
            },
        ],
    }
    response = _post(
        "bundle.json", "application/json", json.dumps(bundle).encode()
    )
    assert response.status_code == 200
    assert "Systolic blood pressure" in response.json()["report_text"]


def test_unsupported_type_is_rejected():
    response = _post("archive.zip", "application/zip", b"PK\x03\x04data")
    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]


def test_empty_file_is_rejected():
    response = _post("empty.txt", "text/plain", b"")
    assert response.status_code == 415


@pytest.mark.parametrize(
    "field", ["profile", "fields_found", "notes", "requires_manual_entry"]
)
def test_response_shape_is_stable(field):
    """The frontend reads these unconditionally."""
    body = _post("report.txt", "text/plain", REPORT.encode()).json()
    assert field in body

#!/usr/bin/env python3
"""Generate sample medical reports for manual testing.

Produces four PDFs spanning the risk spectrum, a FHIR bundle and a plain-text
report — enough to exercise every ingestion path and see the timeline change
shape between a healthy and a high-risk profile.

All patients are fictional. Values are plausible but invented.

    python samples/generate_samples.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas
except ImportError:
    sys.exit(
        "reportlab is required to build the sample PDFs.\n"
        "Install it with:  backend/.venv/bin/pip install reportlab"
    )

OUT_DIR = Path(__file__).resolve().parent


class Report:
    """Minimal flowing-text PDF writer.

    Hand-rolled rather than using Platypus: these are plain key/value lab
    reports, and a page-break-aware line writer is all they need.
    """

    LEFT = inch
    TOP = LETTER[1] - inch
    BOTTOM = inch

    def __init__(self, path: Path, title: str):
        self.canvas = canvas.Canvas(str(path), pagesize=LETTER)
        self.canvas.setTitle(title)
        self.y = self.TOP

    def _ensure_space(self, needed: float) -> None:
        if self.y - needed < self.BOTTOM:
            self.canvas.showPage()
            self.y = self.TOP

    def heading(self, text: str) -> None:
        self._ensure_space(30)
        self.canvas.setFont("Helvetica-Bold", 14)
        self.canvas.drawString(self.LEFT, self.y, text)
        self.y -= 22

    def section(self, text: str) -> None:
        self._ensure_space(26)
        self.y -= 6
        self.canvas.setFont("Helvetica-Bold", 11)
        self.canvas.drawString(self.LEFT, self.y, text)
        self.y -= 16

    def line(self, text: str = "") -> None:
        self._ensure_space(16)
        self.canvas.setFont("Helvetica", 10)
        # Wrap long free-text lines rather than running off the page.
        max_chars = 95
        if len(text) <= max_chars:
            self.canvas.drawString(self.LEFT, self.y, text)
            self.y -= 14
            return
        words, current = text.split(), ""
        for word in words:
            if len(current) + len(word) + 1 > max_chars:
                self.canvas.drawString(self.LEFT, self.y, current)
                self.y -= 14
                self._ensure_space(16)
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            self.canvas.drawString(self.LEFT, self.y, current)
            self.y -= 14

    def save(self) -> None:
        self.canvas.save()


def build_high_risk() -> Path:
    """Multiple compounding risk factors — smoking, night shifts, stress, labs."""
    path = OUT_DIR / "01_high_risk_male_34.pdf"
    r = Report(path, "Annual Health Screening - High Risk")

    r.heading("NORTHGATE OCCUPATIONAL HEALTH")
    r.line("Annual Health Screening Report")
    r.line("Report date: 12 March 2026        Report ID: NH-2026-4471")
    r.line()

    r.section("PATIENT DETAILS")
    r.line("Name: Rajesh Kumar (FICTIONAL - test data)")
    r.line("Sex: male")
    r.line("Age: 34")
    r.line("Occupation: Warehouse supervisor, rotating night shift")

    r.section("VITALS AND MEASUREMENTS")
    r.line("Height: 176 cm")
    r.line("Weight: 94 kg")
    r.line("BMI: 30.3 kg/m2                   [HIGH - obese class I]")
    r.line("Blood pressure: 148/94 mmHg       [HIGH - stage 2 hypertension]")
    r.line("Resting heart rate: 88 bpm")
    r.line("Waist circumference: 104 cm       [HIGH]")

    r.section("LIPID PANEL (fasting)")
    r.line("Total cholesterol: 251 mg/dL      [HIGH]    ref < 200")
    r.line("LDL: 172 mg/dL                    [HIGH]    ref < 100")
    r.line("HDL: 34 mg/dL                     [LOW]     ref > 40")
    r.line("Triglycerides: 224 mg/dL          [HIGH]    ref < 150")

    r.section("METABOLIC PANEL")
    r.line("Fasting glucose: 116 mg/dL        [HIGH]    ref 70-99")
    r.line("HbA1c: 6.1 %                      [HIGH]    ref < 5.7 (prediabetic)")

    r.section("SOCIAL AND LIFESTYLE HISTORY")
    r.line("Smoking: current smoker, 15 cigarettes per day for 14 years")
    r.line("Alcohol: heavy - approximately 20 units per week")
    r.line("Physical activity: sedentary, no structured exercise")
    r.line("Work pattern: rotating night shift, 4 nights on / 3 off")
    r.line("Sleep: 5 hours per night on average, reports poor quality")
    r.line("Stress: high - reports persistent work-related stress")

    r.section("FAMILY HISTORY")
    r.line("Father: myocardial infarction at age 52")
    r.line("Mother: type 2 diabetes, diagnosed age 49")

    r.section("CLINICIAN NOTES")
    r.line(
        "Patient presents with multiple modifiable cardiovascular risk factors. "
        "Smoking cessation discussed. Referred to dietitian. Recommend repeat "
        "lipid panel and HbA1c in 3 months."
    )

    r.save()
    return path


def build_moderate_risk() -> Path:
    """A few soft factors — the interesting middle of the range."""
    path = OUT_DIR / "02_moderate_risk_female_29.pdf"
    r = Report(path, "Wellness Check - Moderate Risk")

    r.heading("RIVERSIDE FAMILY PRACTICE")
    r.line("Routine Wellness Check")
    r.line("Report date: 04 February 2026      Report ID: RF-2026-0912")
    r.line()

    r.section("PATIENT DETAILS")
    r.line("Name: Anjali Menon (FICTIONAL - test data)")
    r.line("Sex: female")
    r.line("Age: 29")
    r.line("Occupation: Software engineer")

    r.section("VITALS AND MEASUREMENTS")
    r.line("Height: 163 cm")
    r.line("Weight: 71 kg")
    r.line("BMI: 26.7 kg/m2                   [HIGH - overweight]")
    r.line("Blood pressure: 128/82 mmHg       [elevated]")
    r.line("Resting heart rate: 74 bpm")

    r.section("LIPID PANEL (fasting)")
    r.line("Total cholesterol: 198 mg/dL      [normal]  ref < 200")
    r.line("LDL: 121 mg/dL                    [borderline] ref < 100")
    r.line("HDL: 52 mg/dL                     [normal]  ref > 40")
    r.line("Triglycerides: 142 mg/dL          [normal]  ref < 150")

    r.section("METABOLIC PANEL")
    r.line("Fasting glucose: 96 mg/dL         [normal]  ref 70-99")
    r.line("HbA1c: 5.5 %                      [normal]  ref < 5.7")
    r.line("Vitamin D: 18 ng/mL               [LOW]     ref 30-100")

    r.section("SOCIAL AND LIFESTYLE HISTORY")
    r.line("Smoking: never smoked")
    r.line("Alcohol: occasional - 3 to 4 units per week")
    r.line("Physical activity: light - walks 20 minutes most days")
    r.line("Work pattern: day shift, largely desk-based")
    r.line("Sleep: 6.5 hours per night")
    r.line("Stress: moderate - reports deadline-driven periods")

    r.section("FAMILY HISTORY")
    r.line("Mother: hypertension, diagnosed age 55")
    r.line("Maternal grandmother: breast cancer, diagnosed age 61")

    r.section("CLINICIAN NOTES")
    r.line(
        "Broadly healthy. Vitamin D deficiency noted - supplementation advised. "
        "Discussed increasing activity toward 150 minutes per week."
    )

    r.save()
    return path


def build_low_risk() -> Path:
    """Baseline case — the timeline should stay flat and low."""
    path = OUT_DIR / "03_low_risk_male_26.pdf"
    r = Report(path, "Health Assessment - Low Risk")

    r.heading("CITYPOINT HEALTH SCREENING")
    r.line("Preventive Health Assessment")
    r.line("Report date: 21 January 2026       Report ID: CP-2026-0233")
    r.line()

    r.section("PATIENT DETAILS")
    r.line("Name: Daniel Osei (FICTIONAL - test data)")
    r.line("Sex: male")
    r.line("Age: 26")
    r.line("Occupation: Secondary school teacher")

    r.section("VITALS AND MEASUREMENTS")
    r.line("Height: 181 cm")
    r.line("Weight: 74 kg")
    r.line("BMI: 22.6 kg/m2                   [normal]")
    r.line("Blood pressure: 114/72 mmHg       [normal]")
    r.line("Resting heart rate: 58 bpm")

    r.section("LIPID PANEL (fasting)")
    r.line("Total cholesterol: 164 mg/dL      [normal]  ref < 200")
    r.line("LDL: 88 mg/dL                     [normal]  ref < 100")
    r.line("HDL: 61 mg/dL                     [normal]  ref > 40")
    r.line("Triglycerides: 76 mg/dL           [normal]  ref < 150")

    r.section("METABOLIC PANEL")
    r.line("Fasting glucose: 84 mg/dL         [normal]  ref 70-99")
    r.line("HbA1c: 5.1 %                      [normal]  ref < 5.7")

    r.section("SOCIAL AND LIFESTYLE HISTORY")
    r.line("Smoking: never smoked")
    r.line("Alcohol: none")
    r.line("Physical activity: active - runs 5 km four times per week")
    r.line("Work pattern: day shift")
    r.line("Sleep: 8 hours per night, reports good quality")
    r.line("Stress: low")

    r.section("FAMILY HISTORY")
    r.line("No significant family history reported.")

    r.section("CLINICIAN NOTES")
    r.line("All markers within normal range. Routine review in 24 months.")

    r.save()
    return path


def build_night_shift() -> Path:
    """Isolates shift work and stress — the scenario you specifically described."""
    path = OUT_DIR / "04_night_shift_nurse_31.pdf"
    r = Report(path, "Occupational Health Review - Shift Worker")

    r.heading("ST BEDE'S HOSPITAL - STAFF HEALTH")
    r.line("Occupational Health Review")
    r.line("Report date: 18 April 2026         Report ID: SB-2026-1188")
    r.line()

    r.section("PATIENT DETAILS")
    r.line("Name: Priya Raman (FICTIONAL - test data)")
    r.line("Sex: female")
    r.line("Age: 31")
    r.line("Occupation: ICU nurse, permanent night shift for 6 years")

    r.section("VITALS AND MEASUREMENTS")
    r.line("Height: 158 cm")
    r.line("Weight: 68 kg")
    r.line("BMI: 27.2 kg/m2                   [HIGH - overweight]")
    r.line("Blood pressure: 138/88 mmHg       [HIGH - stage 1 hypertension]")
    r.line("Resting heart rate: 82 bpm")

    r.section("LIPID PANEL (fasting)")
    r.line("Total cholesterol: 212 mg/dL      [borderline] ref < 200")
    r.line("LDL: 134 mg/dL                    [HIGH]    ref < 100")
    r.line("HDL: 45 mg/dL                     [normal]  ref > 40")
    r.line("Triglycerides: 178 mg/dL          [HIGH]    ref < 150")

    r.section("METABOLIC PANEL")
    r.line("Fasting glucose: 104 mg/dL        [HIGH]    ref 70-99")
    r.line("HbA1c: 5.8 %                      [HIGH]    ref < 5.7 (prediabetic)")
    r.line("TSH: 2.1 mIU/L                    [normal]")

    r.section("SOCIAL AND LIFESTYLE HISTORY")
    r.line("Smoking: never smoked")
    r.line("Alcohol: occasional - 2 units per week")
    r.line("Physical activity: sedentary outside of work")
    r.line("Work pattern: permanent night shift, 12-hour shifts")
    r.line("Sleep: 5.5 hours per day, fragmented daytime sleep")
    r.line("Stress: severe - reports burnout symptoms and emotional exhaustion")

    r.section("FAMILY HISTORY")
    r.line("Father: hypertension, diagnosed age 47")

    r.section("CLINICIAN NOTES")
    r.line(
        "Circadian disruption from sustained night-shift work is a likely "
        "contributor to metabolic and blood pressure findings. Sleep hygiene "
        "counselling provided. Discussed rotation to day shift with line manager."
    )

    r.save()
    return path


def build_fhir_bundle() -> Path:
    """FHIR R4 bundle — exercises the structured ingestion path."""
    path = OUT_DIR / "05_fhir_bundle.json"

    def observation(display: str, value: float, unit: str) -> dict:
        return {
            "resource": {
                "resourceType": "Observation",
                "status": "final",
                "code": {"text": display, "coding": [{"display": display}]},
                "valueQuantity": {"value": value, "unit": unit},
            }
        }

    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "gender": "male",
                    "birthDate": "1988-07-15",
                    "name": [{"family": "Testpatient", "given": ["Arun"]}],
                }
            },
            observation("Systolic blood pressure", 152, "mmHg"),
            observation("Diastolic blood pressure", 96, "mmHg"),
            observation("Body height", 174, "cm"),
            observation("Body weight", 91, "kg"),
            observation("Total cholesterol", 244, "mg/dL"),
            observation("LDL cholesterol", 168, "mg/dL"),
            observation("HDL cholesterol", 36, "mg/dL"),
            observation("Triglycerides", 210, "mg/dL"),
            observation("Hemoglobin A1c", 6.3, "%"),
            observation("Fasting glucose", 121, "mg/dL"),
            {
                "resource": {
                    "resourceType": "Condition",
                    "code": {
                        "text": "Essential hypertension",
                        "coding": [{"display": "Essential hypertension"}],
                    },
                }
            },
            {
                "resource": {
                    "resourceType": "Condition",
                    "code": {
                        "text": "Tobacco use disorder",
                        "coding": [{"display": "Tobacco use disorder"}],
                    },
                }
            },
            {
                "resource": {
                    "resourceType": "MedicationRequest",
                    "status": "active",
                    "medicationCodeableConcept": {"text": "Amlodipine 5mg daily"},
                }
            },
        ],
    }

    path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return path


def build_text_report() -> Path:
    """Plain text — the fastest path to test with, and the local-model default."""
    path = OUT_DIR / "06_plain_text_report.txt"
    path.write_text(
        """COMMUNITY HEALTH CENTRE - SCREENING SUMMARY
Report date: 09 May 2026

PATIENT
Name: Meera Iyer (FICTIONAL - test data)
Sex: female
Age: 38
Occupation: Retail manager

VITALS
Height: 160 cm
Weight: 79 kg
BMI: 30.9 kg/m2 [HIGH]
Blood pressure: 144/90 mmHg [HIGH]

LABORATORY
Total cholesterol: 232 mg/dL [HIGH]
LDL: 149 mg/dL [HIGH]
HDL: 41 mg/dL [normal]
Triglycerides: 196 mg/dL [HIGH]
HbA1c: 6.4 % [HIGH - prediabetic]
Fasting glucose: 118 mg/dL [HIGH]

LIFESTYLE
Smoking: former smoker, quit 3 years ago, 10 pack-year history
Alcohol: moderate
Physical activity: sedentary
Work pattern: rotating shift
Sleep: 6 hours per night
Stress: high

FAMILY HISTORY
Mother: type 2 diabetes diagnosed age 44
Brother: type 2 diabetes diagnosed age 41

NOTES
Strong family history of type 2 diabetes combined with prediabetic HbA1c.
Structured lifestyle intervention recommended.
""",
        encoding="utf-8",
    )
    return path


def main() -> None:
    builders = (
        build_high_risk,
        build_moderate_risk,
        build_low_risk,
        build_night_shift,
        build_fhir_bundle,
        build_text_report,
    )

    print("Generating sample reports...\n")
    for build in builders:
        path = build()
        size_kb = path.stat().st_size / 1024
        print(f"  {path.name:34s} {size_kb:6.1f} KB")

    print(f"\nWrote {len(builders)} files to {OUT_DIR}")
    print("\nAll patients are fictional. Values are plausible but invented.")


if __name__ == "__main__":
    main()

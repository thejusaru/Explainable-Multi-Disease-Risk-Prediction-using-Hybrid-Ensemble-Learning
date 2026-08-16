# Sample reports

Fictional patients for manual testing. Values are plausible but invented — no
real person's data is here.

Regenerate with `./run.sh samples`.

| File | Patient | What it exercises |
|---|---|---|
| `01_high_risk_male_34.pdf` | Male, 34 | Smoking + obesity + hypertension + prediabetes + night shift + family history. Should produce steep, clearly rising curves. |
| `02_moderate_risk_female_29.pdf` | Female, 29 | Overweight, borderline LDL, low vitamin D, family history of breast cancer. The interesting middle of the range. |
| `03_low_risk_male_26.pdf` | Male, 26 | Everything normal, active, non-smoker. Curves should stay flat and low — the sanity check that the model isn't inflating risk. |
| `04_night_shift_nurse_31.pdf` | Female, 31 | Isolates shift work and severe stress: never-smoker with 6 years of permanent nights, elevated BP and HbA1c. |
| `05_fhir_bundle.json` | Male, 37 | FHIR R4 ingestion — Patient, Observation, Condition and MedicationRequest resources. Age is derived from `birthDate`, not stated. |
| `06_plain_text_report.txt` | Female, 38 | Plain text. Fastest to test with, and the best starting point for local models. |

## Suggested test sequence

1. **`03_low_risk`** first — confirms low inputs give low outputs. If a healthy
   26-year-old comes back at 40% risk of anything, the engine is inflating.
2. **`01_high_risk`** next — the same UI with obviously steeper curves. Check
   that `drivers` names the actual facts ("current smoker, 15/day"), not
   "lifestyle factors".
3. **`04_night_shift`** — should surface circadian disruption and stress rather
   than defaulting to smoking, since this patient has never smoked.
4. **`05_fhir_bundle`** — confirms the structured path works and age is derived.
5. **Same file twice** — the numbers will differ between runs. That is expected
   and is the main limitation of LLM-based estimation.

## Testing image upload

There is no sample image, because a screenshot of a PDF is a poor test of a real
photo. To test the vision path, open any sample PDF and screenshot it, or
photograph a printout. Note that **image upload requires the Claude engine** —
local text models cannot read images and the app will tell you so rather than
analysing a blank.

## Comparing engines

Run the same file through both to see the difference:

1. Select **Claude (cloud)**, upload `01_high_risk_male_34.pdf`, note the curves.
2. Switch to **Local model (Ollama)**, upload the same file.

Expect the local model to be less differentiated between conditions, occasionally
retried on malformed output, and slower on CPU. If it gives several conditions
identical probabilities, the app flags that under "Data quality" — the numbers
are unreliable when that happens.

### What a 7B model actually gets wrong

Measured on `qwen2.5:7b` with these samples, so you know what you're looking at:

- **Duplicate curves.** Several conditions given the same five probabilities,
  meaning it never estimated them separately. The app detects and flags this.
- **Inflated baselines.** `03_low_risk` (healthy, active, non-smoking 26-year-old)
  came back at 28% for type 2 diabetes at 45 — far too high.
- **Sex-inappropriate conditions.** It reported breast cancer risk for a male
  patient. Nothing validates clinical appropriateness, so this passes through.
- **Retries.** Malformed JSON on the first attempt happens; the engine retries
  once with the error fed back before failing.

None of these appear with the Claude engine. Use a local model to prove the
switch works and to develop offline — not to judge the quality of the product.

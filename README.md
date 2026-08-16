# Health Risk Projection

Feed in a patient medical report and get estimated disease risk at ages 25, 30,
35, 40 and 45 — with the factors driving each risk and what to do about them.
Runs against **Claude** (cloud) or a **local model** via Ollama (Llama, Qwen,
Mistral), switchable in the UI.

**This is not a diagnostic tool.** It produces statistical estimates from an AI
language model. See [Limitations](#limitations) before showing it to anyone.

## Quick start

```bash
./run.sh
```

Installs dependencies, generates the sample reports, checks which engines are
available, and starts both servers. Open <http://localhost:3000>.

| Command | What it does |
|---|---|
| `./run.sh` | Set up if needed, then start backend + frontend |
| `./run.sh setup` | Install dependencies only |
| `./run.sh check` | Report environment status without starting anything |
| `./run.sh test` | Run the backend test suite |
| `./run.sh samples` | Regenerate the sample reports |
| `./run.sh stop` | Kill anything left on the app ports |

You need **at least one engine** configured — see below. `./run.sh check` tells
you what's missing.

### Claude (cloud)

```bash
cp backend/.env.example backend/.env    # then add your ANTHROPIC_API_KEY
```

Best quality: schema-enforced output, and the only engine that reads images.

### Local model (Ollama)

```bash
ollama serve            # in a separate terminal
ollama pull qwen2.5:7b
```

Runs offline with no API cost. Less reliable — see
[Engine comparison](#engine-comparison).

## Using it

Three pages:

| Page | What it does |
|---|---|
| `/` | Upload a report → parsed values fill the form → review and correct → analyse |
| `/settings` | Choose the analysis model and theme; changes staged until you save |
| `/results` | The finished risk projection |

**The flow is extract → review → analyse.** Dropping a report calls
`/api/extract`, which reads it and returns what it found; those values populate
the form and are highlighted as *from report*. You correct anything wrong, then
click Analyse — so a misread blood pressure gets caught by a human rather than
silently skewing the estimate. Editing an auto-filled field clears the
highlight, since the value is then yours rather than the document's.

While the assessment runs, a modal shows a loader and elapsed time. When it
finishes it waits for you to click **View report** rather than yanking the page
away.

Theme (light / dark / system) and model choice persist in the browser. The
active model is always visible in the header and one click from `/settings`.

## Testing it

Six sample reports are generated into [`samples/`](samples/) — see
[samples/README.md](samples/README.md) for what each one exercises and a
suggested test order. Start with `03_low_risk_male_26.pdf` (curves should stay
low), then `01_high_risk_male_34.pdf` (they should rise steeply).

## Stack

- **Backend** — Python 3.11+, FastAPI, Claude API (`claude-opus-5`), Ollama
- **Frontend** — Next.js 15, React 19, TypeScript, hand-rolled SVG chart

## Engine comparison

| | Claude (cloud) | Local (Ollama) |
|---|---|---|
| Output shape | Guaranteed by structured outputs | Best-effort; repaired and retried |
| Images | Yes, via vision | **No** — rejected with a clear message |
| Speed | ~30–60s | ~45s–3min on CPU |
| Cost | Per token | Free |
| Network | Required | Fully offline |
| Reliability | High | Degrades sharply below ~7B params |

The local engine compensates where it can: it repairs percentages written as
`15` instead of `0.15`, fills missing age buckets, normalises invalid enum
values, and retries once with the validation error fed back. What it cannot fix,
it reports — if the model gives several conditions identical probabilities
(observed with `qwen2.5:7b`), that's flagged in the UI as unreliable rather than
rendered as a confident chart.

## Inputs

| Input | How it's handled |
|---|---|
| **Structured form** | Sent directly as a `PatientProfile`. Most reliable. Also the review surface for everything below. |
| **PDF lab report** | Text extracted with `pypdf`. Scanned PDFs with no text layer are rejected with a message telling the user to upload an image instead. |
| **Image / photo** | Base64-encoded and passed to Claude's vision model — no local OCR dependency. Claude engine only. |
| **FHIR JSON** | `Patient`, `Observation`, `Condition` and `MedicationRequest` resources are flattened to text. Accepts a Bundle or a bare resource. |

Uploads cap at 25 MB. A form profile and a file can be submitted together — the
user's typed values take precedence over anything read from the report.

## Tests

```bash
./run.sh test
```

64 tests covering the schemas, all four ingestion paths, and both engines'
post-processing. Both model clients are stubbed, so tests need no API key, no
running Ollama, and cost nothing.

## Architecture

```
run.sh                    One-command setup + run
samples/                  Fictional test reports + generator

frontend/
  app/page.tsx            Intake: upload → review → analyse
  app/settings/page.tsx   Model + theme, staged until saved
  app/results/page.tsx    The finished report
  app/globals.css         Design tokens, light + dark
  lib/types.ts            Mirrors the backend schemas
  lib/settings.tsx        Theme + model prefs (localStorage)
  lib/analysis-store.tsx  Carries the report between pages (sessionStorage)
  components/             AppHeader, ReportUpload, IntakeForm,
                          ProcessingModal, RiskTimeline (SVG), Results

backend/app/
  models/schemas.py       Pydantic contracts + validation invariants
  parsers/extract.py      PDF / image / FHIR / text ingestion
  engines/base.py         RiskEngine interface  ← the swap point
  engines/llm_engine.py   Claude-backed implementation
  engines/local_engine.py Ollama-backed implementation
  routers/analysis.py     POST /api/analyze/{profile,report}
  routers/engines.py      GET /api/engines — availability discovery
  dependencies.py         Maps engine choice to implementation
```

### Adding another engine

Risk computation sits behind `RiskEngine` (`engines/base.py`) — a single
`assess()` method. To add clinical risk models (Framingham, ASCVD, FINDRISC,
QRISK3):

1. Add `engines/clinical_engine.py` implementing `RiskEngine.assess`.
2. Add a value to `EngineKind` in `config.py` and a branch in `dependencies.py`.

No route, schema or frontend changes — the picker populates from
`/api/engines`. The `engine` and `model` fields on every assessment record which
one produced it, so past results stay auditable.

## Guardrails

Engine output is post-processed before it reaches the UI:

- **Schema validation** — every condition must cover exactly the five projection
  ages. A malformed response is a 502, not a gap-toothed chart.
- **Monotonic clamping** — cumulative risk cannot decrease with age, so dips are
  clamped rather than rendered.
- **Confidence capping** — a profile with fewer than four known fields cannot
  yield "high" confidence. Local models are capped at "medium" regardless.
- **Duplicate-curve detection** — identical probabilities across conditions are
  flagged as unreliable (local models only).
- **Refusal handling** — `stop_reason` is checked before reading content, so a
  model refusal surfaces as a clear error instead of an index crash.
- **Unknown fields omitted from the prompt** — rendering `Smoking: None` would
  read to the model as an assertion the patient doesn't smoke.

## Limitations

Read these before demoing.

1. **Numbers are not reproducible.** The same report analysed twice will give
   different percentages — often several points apart. Sampling parameters are
   rejected on Opus 5, so there is no `temperature=0` fix. This is inherent to
   LLM-only estimation.
2. **Numbers are not clinically validated.** They are the model's judgment, not
   the output of a cohort-validated risk equation. Treat them as illustrative.
3. **Local models are materially worse.** A 7B model produces less
   differentiated estimates and sometimes gives several conditions the same
   curve. Use Claude for anything you intend to show someone.
4. **Not a medical device.** No regulatory clearance. Do not use for triage,
   screening or any treatment decision.
5. **PDF text extraction only.** No local OCR — scanned PDFs must be uploaded as
   images, which requires the Claude engine.
6. **No persistence.** Nothing is stored; every analysis is a fresh call. Adding
   a database means adding a considered stance on medical-data retention.

The path to fixing (1) and (2) is the clinical-engine swap described above.

## Troubleshooting

**`pip install` fails with `SSLError ... ssl module is not available`**
Your Python was built against a missing OpenSSL. `run.sh` avoids this by probing
for a working interpreter, but if you set up manually, check with
`python3 -c 'import ssl'` and use another build (`brew install python@3.13`).

**"Could not reach the API"**
The backend isn't running or is on another port. `./run.sh check`.

**"Ollama not reachable"**
Run `ollama serve` in a separate terminal, then `ollama pull qwen2.5:7b`.

**Local analysis times out**
CPU inference is slow. Try a smaller model (`llama3.2`), or raise
`LOCAL_TIMEOUT_SECONDS` in `backend/.env`.

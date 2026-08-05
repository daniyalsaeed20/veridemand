# Phase 5 final implementation report (consolidation)

Consolidation report for Phase 5 handwriting-routing evidence after Tasks 1–3,
A–B4, C0–C3, and Task D clean-environment release gates.

**Starting HEAD (Task D):** `6f32b26eaf305803d81111c6aab2b81a8f05c498`  
**Branch:** `phase-05-handwriting-routing`  
**Descends from Phase 4 v2.1:** `2e77590432f21ebda2cdcf4feb3f67aaefd45cea`  
**C3 ancestry:** `6f55dd8` → `b76e135` → `8b2663b` → `6f32b26`

**Annotated tag (when PASSED):** `phase-5-handwriting-routing-v1`

**Release decision: PHASE 5 PASSED** — delivers conservative image-dominant
full-page reservation for Phase 6 vision processing. Does **not** deliver a
production region handwriting classifier, handwriting transcription, or a
vision-provider integration.

---

## Scope

### Delivered (current release path)

```text
existing Phase 4 page evidence
    ↓
page_is_image_dominant
    ↓
fallback enabled + image-dominant
    → local Paddle recognition prohibited
    → canonical full-page render preserved
    → full-page geometry [0,0,1,1]
    → page route vision_reserved_pending_phase_6
    → document lifecycle awaiting_phase_6
otherwise
    → existing Phase 4 processing unchanged
```

Feature default: `HANDWRITING_PAGE_VISION_FALLBACK_ENABLED=false`.  
Mode: `conservative` only (hybrid rejected at settings validation).

### Not delivered

- Region crop → ONNX classifier → selective Paddle recognition (original plan)
- Handwriting transcription / local HTR
- OpenAI or any vision-provider call
- Contact sheets
- Phase 6 provider adapter or completion transition
- Final document structure (tables/forms/reading order)
- Universal handwriting detection
- Production region classifier package (`production_candidate`)

### Source of Truth / roadmap variance

The frozen Source of Truth and roadmap describe Phase 5 as **region-level**
handwriting classification with routing recall exit gates. Experimentation did
not clear those gates. Task C3 / Task D release the **conservative page-level
safety fallback** instead. This variance is intentional and documented in ADRs
0082–0087; frozen SoT files were not edited.

---

## Decision history

| Stage | Outcome |
|-------|---------|
| Classifier foundation (Task 2) | Runtime package contract + optional health; router default off |
| Annotation / seeds (3A–A2) | Prototype labels; 55 confirmed handwriting seeds on 9 pages |
| Three-class softmax (B) | Failed safety gates |
| ASAP-supplemented softmax (B2) | Still unsafe; CC BY ASAP attribution recorded |
| Dual-risk independent heads (B3) | `SAFETY-FIRST MODEL STILL NOT SAFE` |
| Route-first model (B4) | `ROUTE-FIRST MODEL STILL NOT SAFE` |
| Detector-first shadow (C0) | Offline only; live path unchanged |
| Detector calibration (C1) | `DETECTOR COVERAGE STILL INSUFFICIENT` (best incomplete recall; 7 misses) |
| Page fallback feasibility (C2) | Feasible; C2 historically recommended hybrid |
| Conservative page reservation (C3) | Shipped Strategy 1; hybrid deferred (ADR 0087) |
| Consolidation (Task D) | Clean OCR-only gates; final release decision |

Failed region-model experiments remain valid design history. They are **not**
shipped runtime functionality. ADRs 0054–0071 and 0077–0081 Status lines mark
them superseded/rejected/insufficient for the current release path; ADRs
0082–0087 are the current release architecture.

---

## Architecture

- Predicate: existing Phase 4 `page_is_image_dominant`
- Exclusive page route: `vision_reserved_pending_phase_6`
- Document lifecycle when any page is reserved: `awaiting_phase_6`
- Progress overall maximum remains **65%**
- Reserved pages: Phase 5 routing complete; final extraction incomplete
- No live ONNX classifier; no live server detector; no vision provider
- Hybrid page OCR deferred until a safe region router exists

Primary docs:

- [phase-5-page-vision-reservation.md](../architecture/phase-5-page-vision-reservation.md)
- [phase-5-page-reservation.md](../operations/phase-5-page-reservation.md)
- [phase-5-page-vision-reservation-acceptance.md](../evaluation/phase-5-page-vision-reservation-acceptance.md)
- ADRs 0082–0087

---

## Feature flag

| Profile | `HANDWRITING_PAGE_VISION_FALLBACK_ENABLED` | Mode |
|---------|--------------------------------------------|------|
| Default / Phase 4 production | `false` | `conservative` |
| Acceptance / Phase 6 prep | `true` | `conservative` |

Unsupported modes (for example `hybrid`) fail settings validation loudly.

---

## Contracts

- `PageRoute.VISION_RESERVED_PENDING_PHASE_6`
- `VisualProcessingStatus.AWAITING_PHASE_6` / `DocumentStatus.AWAITING_PHASE_6`
- `PageVisionReservationEvidence` (full-page geometry; no final text)
- Exclusive `final_route_histogram` includes `vision_reserved_pending_phase_6_pages`
- Frontend labels: reserved route + awaiting lifecycle; not shown as completed
- Contracts generate/check: PASS (OCR-only Task D run)

---

## Acceptance results (feature-on, private safe aggregates)

Re-run: `uv run --group ocr python scripts/phase5/page_vision_reservation_acceptance.py`  
Decision: `PAGE-LEVEL VISION RESERVATION ACCEPTANCE PASSED`

| Aggregate | Value |
|-----------|------:|
| Pages | 215 |
| Reserved | 107 |
| Non-reserved | 108 |
| Reservation rate | 49.77% |
| Documents / source groups affected | 3 / 3 |
| Known handwriting pages reserved | 9 / 9 |
| Confirmed handwriting seeds covered | 55 / 55 |
| Task C1 miss seeds covered | 7 / 7 |
| Paddle recognition calls on reserved pages | 0 |
| Vision-provider calls | 0 |
| Reserved pages marked fully complete | 0 |
| Overall progress maximum | 65% |

Non-reserved family histogram: other 97, billing_ledger 10, image_document 1.

No private filenames, IDs, OCR text, images, or paths recorded.

---

## Feature-off regression

Environment: `.venv-ocr` (`UV_PROJECT_ENVIRONMENT=.venv-ocr`, `--group ocr`),  
`HANDWRITING_PAGE_VISION_FALLBACK_ENABLED=false`.

| Gate | Result |
|------|--------|
| Backend unit tests | 674 passed, 7 skipped |
| Frontend unit tests | 152 passed (24 files) |
| OCR runtime verify | PASS |
| OCR integration | 2 passed |
| Critical smoke (`--critical-subset`) | 6 passed, 1 future-phase skip, 0 failed |
| Phase 4 smoke (`--phase4-subset`) | 8/8 passed |
| `/health/live` + `/health/ready` | ready; paddle pass; classifier/openai not_configured |
| Residual sessions | PASS |
| E2E | 20 passed, 5 skipped (after OCR-only Playwright fix) |

Feature-off asserts: no `vision_reserved_pending_phase_6` reservation path when
the flag is off (unit coverage); Phase 4 route accounting and progress behaviour
unchanged.

---

## Progress and scheduling

- Overall maximum remains **65%** (`OVERALL_CAP`)
- Progress never decreases; heartbeats do not advance progress
- Reserved-page materialisation does not imply extraction complete / 100%
- Reserved pages never enter Paddle recognition workers / OCR permits
- Fair scheduling retained for non-reserved OCR pages
- Cancellation and session TTL/reset cleanup unchanged

---

## Reliability

| Check | Result |
|-------|--------|
| `/health/ready` OCR-only feature-off | PASS |
| `/health/ready` OCR-only feature-on | PASS (classifier/openai still not_configured) |
| Cancellation E2E | PASS |
| Residual session check | PASS |
| Build-identity smoke | PASS against matching HEAD |

Page reservation adds **no** model requirement for readiness.

---

## Security

Confirmed for Task D consolidation:

- No private page image / crop / manifest tracked
- No OCR text or private IDs in reports
- No screenshot or montage
- No provider credential; no external page upload; no OpenAI / vision call
- No raw public training data tracked; ASAP CC BY attribution retained for
  experimental use only
- Failed ONNX artefacts not shipped as production packages
- Reserved artefacts follow session TTL/reset cleanup
- ONNX Runtime remains inventoried; Torch/Torchvision model-dev only; Paddle
  OCR-only; OpenCV / HTR engines absent
- Dependency-boundary and private-corpus guards PASS
- No regulatory-compliance claim

See [phase-5-security-review.md](../security/phase-5-security-review.md).

---

## Environments

### OCR acceptance (required for release gates)

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-ocr"
uv sync --group ocr
# torch / torchvision must be absent; paddle must import
uv run --group ocr python scripts/verify_ocr_runtime.py
```

Playwright prefers `.venv-ocr` when present (`frontend/playwright.config.ts`) so
E2E does not load a mixed Torch+Paddle `.venv` (Windows `shm.dll` conflict).

### Model-development (offline only)

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-model-dev"
uv sync --group model-dev
```

Torch available; Paddle success not required on Windows. Task D does not retrain.

Windows DLL conflict is avoided by keeping these environments separate.

---

## Tests and gates (Task D)

| Command | Environment | Result | Notes |
|---------|-------------|--------|-------|
| `uv lock --check` | `.venv-ocr` | PASS | Via `check_all` |
| `ruff format --check` / `ruff check` / `mypy` | `.venv-ocr` | PASS | Via `check_all` |
| `uv run pytest` | `.venv-ocr` | PASS | 674 passed, 7 skipped |
| `pnpm contracts:generate` / check | `.venv-ocr` | PASS | Deterministic; no drift |
| Frontend format/lint/typecheck/test/build | node | PASS | 2 eslint warnings (pre-existing) |
| Dependency-boundary / private-corpus / legacy-scope | `.venv-ocr` | PASS | |
| OCR verify + OCR integration | `.venv-ocr` | PASS | |
| `pnpm -C frontend test:e2e` (first `check_all`) | mixed `.venv` | FAIL | `shm.dll` / Torch in default `.venv` |
| `pnpm -C frontend test:e2e` (rerun) | `.venv-ocr` preferred | PASS | 20 passed, 5 skipped |
| Residual sessions | `.venv-ocr` | PASS | After e2e |
| Critical smoke feature-off | API `:8020` OCR-only | PASS | 6 pass + 1 future skip |
| Phase 4 smoke feature-off | API `:8020` OCR-only | PASS | 8/8 |
| Page reservation acceptance feature-on | `.venv-ocr` | PASS | 215/107/108; 9/9; 55/55; 7/7 |
| Route + reservation unit tests | `.venv-ocr` | PASS | 18 passed |
| `/health/ready` feature-on | API `:8021` OCR-only | PASS | |

Skipped ≠ passed. The only first-run failure was E2E against a mixed Windows
venv; Task D’s environment isolation fix made the clean rerun green.

---

## Known limitations

- Only **nine** confirmed handwriting pages / **55** seeds in private evidence
- No universal handwriting-detection claim
- Approximately half of private pages are reserved (~49.8%)
- No production region classifier
- No Phase 6 provider; no handwriting transcription
- Detector fine-tuning remains optional future optimisation
- Hybrid mode remains deferred (ADR 0087)
- Region-level router remains unshipped
- Six-group release held-out freeze remains a later decision

---

## Phase 6 handoff (consume only — not implemented)

Phase 6 may consume, for each reserved page:

- Canonical page render reference
- Page index
- Full-page geometry `[0,0,1,1]`
- Reservation reason / evidence
- Pending lifecycle `awaiting_phase_6`
- Provisional extraction evidence already produced for non-reserved pages

Phase 6 must supply the vision provider, transcription, and completion
transition. Phase 5 does not implement that adapter.

---

## Release decision

| Field | Value |
|-------|-------|
| Starting HEAD | `6f32b26eaf305803d81111c6aab2b81a8f05c498` |
| Delivered behaviour | Conservative image-dominant full-page reservation |
| Annotated tag | `phase-5-handwriting-routing-v1` |
| Phase 6 start | Unblocked for planning; not started by this report |

```text
PHASE 5 PASSED
```

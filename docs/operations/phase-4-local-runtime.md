# Phase 4 local runtime (operator guide)

Local setup and verification for Phase 4 visual detection and printed OCR.
Privacy rule: never print private document text, filenames, or page images in
logs or operator notes. Use opaque labels only for private cases.

## Prerequisites

- Node.js matching `package.json` engines (`>=24.18.0 <25`)
- `pnpm` (packageManager pin in root `package.json`)
- `uv` for the Python backend
- LibreOffice Writer on `PATH` (or `LIBREOFFICE_EXECUTABLE`) for DOC/DOCX
- Disk space for `.models/paddleocr/` (gitignored)

## Setup

```bash
pnpm install
uv sync
# Optional OCR dependency group (required for printed OCR readiness):
uv sync --group ocr
```

Copy or create a local `.env` only if you need non-default settings. Defaults
include:

| Setting | Default | Notes |
|---------|---------|-------|
| API | `127.0.0.1:8000` | `pnpm dev:backend` (non-OCR) or `pnpm dev:backend:ocr` |
| Frontend | Vite (typically `5173`) | CORS allowlist is `FRONTEND_ORIGIN` |
| `OCR_DETECTION_MODEL_NAME` | `PP-OCRv5_mobile_det` | ADR 0023 |
| `OCR_RECOGNITION_MODEL_NAME` | `PP-OCRv5_mobile_rec` | ADR 0023 |
| `OCR_WORKERS` | `1` | Max 2 |
| Progress cap | 65% | Contract and coordinator enforced |
| `FAIR_OCR_SCHEDULING_ENABLED` | `true` | Set `false` for FIFO |
| `SESSION_TTL_SECONDS` | `7200` | Runtime sessions only |

PP-OCRv6 medium remains available via settings for comparison benchmarks
(ADR 0018). Models are never downloaded during document processing.

## Bootstrap and verify OCR models

```bash
pnpm models:ocr:bootstrap
pnpm models:ocr:verify
# Alias:
pnpm verify:visual-runtime
```

Bootstrap writes `.models/paddleocr/model-record.json`. Readiness fails if
required models are missing while OCR is enabled. See
[phase-4-ocr-models.md](../models/phase-4-ocr-models.md).

## Start the stack

```bash
pnpm dev
# or separately:
pnpm dev:backend
pnpm dev:frontend
```

Prefer a **single** dedicated API process. Multiple `uvicorn --reload`
instances fighting over port 8000 cause identity and smoke failures.

Do not bind a long-lived smoke API on port **8010** — Playwright
`chromium-holds` e2e uses that port.

## Build identity (`/health/live`)

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/live" | ConvertTo-Json -Depth 10
```

Privacy-safe fields include `git_commit`, `process_id`,
`application_version`, `worker_generation`, and `configuration_profile`.

Smoke and acceptance runners default to `--require-build-identity`
(see [smoke README](../smoke/README.md)). The live `git_commit` must match
repository `HEAD`. On mismatch, gates fail with a diagnostic; they **never**
kill unrelated processes.

Helpers live in `scripts/lib/api_process_guard.py`.

## Readiness

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/ready" | ConvertTo-Json -Depth 20
# or:
curl.exe -s http://127.0.0.1:8000/health/ready
```

A `200` ready response means required OCR models and workers are up. It does
not by itself prove multipage progress correctness or private acceptance.

## Stopping the correct process

1. Read `/health/live` and note `process_id` and `git_commit`.
2. Confirm the PID belongs to the VeriDemand API you started (Task Manager /
   `Get-Process` / equivalent).
3. Stop **that** process only (Ctrl+C in its terminal, or end the matching PID).
4. Never kill an unrelated listener on the port. If the port is occupied by a
   mismatched or unknown process, free it manually after identifying the owner,
   or start the API on a dedicated free port and set `VERIDEMAND_API_BASE`.

Identity mismatch fails gates; port isolation never auto-kills strangers.

## Session reset

- Use the product session reset / delete flows, or wait for TTL cleanup
  (`SESSION_TTL_SECONDS`, periodic sweep).
- After tests, confirm no residual trees under `temp/` via
  `uv run python scripts/check_no_residual_sessions.py` (also part of
  `pnpm check`).
- Runtime data is not restored after browser refresh.

## Readiness failures (quick)

| Symptom | First checks |
|---------|----------------|
| OCR not ready | `pnpm models:ocr:verify`; `OCR_ENABLED`; model names vs `.models/` |
| LibreOffice missing | Install Writer; set `LIBREOFFICE_EXECUTABLE` |
| WASM / blank PDF.js | `pnpm check:wasm` / `verify_pdfjs_wasm.py --sync --clean` |
| Build identity mismatch | Stop obsolete API; restart from current `HEAD` |
| Port conflict | Identify PID; do not kill unknowns blindly |

See [phase-4-troubleshooting.md](phase-4-troubleshooting.md).

## Routing counts and page indices

After processing, inspect privacy-safe aggregates only (route counts, page
counts, durations, reason codes). Do not dump transcripts.

Distinguish:

| Field | Meaning |
|-------|---------|
| `document_page_number` | Absolute 1-based canonical page |
| `document_pages_total` | Canonical page count |
| `selected_page_index` | 1-based index within current work category |
| `selected_pages_total` | Count selected for that category |
| `visual_page_index` / `visual_pages_total` | Selected visual OCR subset |

Never pair absolute `page_number` with a selected-work `pages_total` as if they
shared one coordinate system (ADR 0029 /
[phase-4-progress-events.md](../architecture/phase-4-progress-events.md)).

## Safe diagnostics

Allowed: request/session/document IDs, stages, durations, page counts, model
names, warning/error codes, route histograms, RSS aggregates.

Forbidden in default logs and operator paste: full extracted text, page images,
crop contents, private filenames/paths, OCR hypothesis strings.

`GET .../native/pages/{n}?include_verification_candidates=false` is the default.
Enable verification candidates only for intentional diagnostics.

Test-only flags (`OCR_INJECT_VISUAL_FAILURE`, queue/native test delays) must
remain **false / 0** outside controlled acceptance.

## Supported root scripts (`package.json`)

| Script | Purpose |
|--------|---------|
| `pnpm dev` | Backend + frontend concurrently (does not force `.venv-ocr`) |
| `pnpm dev:ocr` | OCR-only backend (`.venv-ocr`) + frontend |
| `pnpm dev:backend` | Uvicorn on `127.0.0.1:8000` (default uv env) |
| `pnpm dev:backend:ocr` | Uvicorn from `.venv-ocr` with Torch refusal |
| `pnpm dev:frontend` | Vite frontend |
| `pnpm models:ocr:bootstrap` | Download/bootstrap OCR models |
| `pnpm models:ocr:verify` | Verify OCR runtime + model record |
| `pnpm verify:visual-runtime` | Alias of OCR verify |
| `pnpm verify:windows-dev-runtime` | Windows dev runtime checks |
| `pnpm diagnose:mkldnn` | Windows MKLDNN diagnostics |
| `pnpm smoke:corpus` | Synthetic smoke (page-by-page default) |
| `pnpm smoke:corpus:whole` | Whole-document smoke |
| `pnpm smoke:corpus:page` | Page-by-page smoke |
| `pnpm smoke:corpus:test-id` | Single test ID (pass `-- Txx`) |
| `pnpm smoke:corpus:validate` | Validate PDF/manifest only |
| `pnpm smoke:corpus:critical` | PR critical native subset |
| `pnpm smoke:corpus:phase4` | Phase 4 visual subset |
| `pnpm contracts:generate` | Regenerate OpenAPI + Zod |
| `pnpm contracts:check` | Drift / determinism check |
| `pnpm test` | Backend pytest + frontend unit tests |
| `pnpm test:e2e` | Playwright e2e |
| `pnpm test:ocr` | OCR-filtered pytest |
| `pnpm test:ocr:integration` | OCR integration tests |
| `pnpm evaluate:ocr` | Synthetic printed OCR eval |
| `pnpm check` | Full local gate suite (`check_all.py`) |
| `pnpm check:legacy` | No legacy demand-letter scope |
| `pnpm check:private` | No private corpus in git |
| `pnpm check:wasm` | Sync/verify PDF.js WASM |
| `pnpm format` / `format:check` / `lint` / `typecheck` / `build` | Quality tooling |

## Architecture pointer

Pipeline order and ADR index:
[phase-4-overview.md](../architecture/phase-4-overview.md).

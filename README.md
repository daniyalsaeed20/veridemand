# VeriDemand

VeriDemand is a **document-extraction platform**. It extracts text and structure
from documents using a deterministic pipeline (native text and OCR, with a
vision LLM only for handwritten or uncertain regions). This repository has
completed **Phase 4**: visual detection, printed OCR, hybrid page routing,
targeted repair, progress/ETA, and fair scheduling (progress capped at **65%**).
Do not start Phase 5 until the Phase 4 release exit gates are green.

> **Runtime-only product.** VeriDemand keeps uploaded files and results only for
> the duration of a session. Refreshing, closing, or resetting the page may
> permanently remove everything. Nothing is persisted to a database or browser
> storage; a server restart or refresh starts a fresh session.

The sole authoritative specification is
[`docs/SOURCE_OF_TRUTH.md`](docs/SOURCE_OF_TRUTH.md).
Phase 4 overview:
[`docs/architecture/phase-4-overview.md`](docs/architecture/phase-4-overview.md).

## Phase 4 scope

Building on Phase 3, Phase 4 includes:

- **Page rendering** with pypdfium2 (one page at a time).
- **Native visibility probes** for accepted natives (retain or downgrade).
- **Printed OCR** via local PaddleOCR in a long-lived worker (`OCR_WORKERS=1`).
- **Hybrid routing**, verified embedded OCR, targeted regional repair, dense-form
  quality gate, selected OCR pass, fair page-quantum scheduling.
- Progress capped at **65%**. Handwriting and final structure are **not** evaluated.

Default Settings models are `PP-OCRv5_mobile_*` ([ADR 0023](docs/decisions/0023-adaptive-ocr-render-mobile-baseline.md)).
Product calibration docs may reference PP-OCRv6 medium
([ADR 0018](docs/decisions/0018-paddleocr-local-inference.md)).

### Not implemented yet (Phase 5+)

Handwriting classification / HTR, vision-LLM calls, final reading order, final
table/form reconstruction, search, databases, Redis/Celery, and authentication.

## Repository layout

```text
backend/    FastAPI app (editable package) + tests
frontend/   Vite + React + TypeScript app (pnpm workspace)
docs/       Source of truth, architecture, ADRs, contracts, dependencies, phases
scripts/    Contract generation, smoke, acceptance, validation orchestration
models/ fixtures/ temp/   Scaffolding / gitignored private fixtures
```

## Prerequisites

- **uv** (Python **3.12** environment).
- **Node.js 24.18.0** (`.nvmrc`) with **Corepack** enabled.
- **pnpm 11** (pinned via `packageManager`).
- **LibreOffice** (Writer) for Word canonicalisation — see `.env.example`.

## Setup

```bash
uv sync --all-groups
pnpm install
```

Copy `.env.example` to `.env` (root) and `frontend/.env.example` to
`frontend/.env` if you need to override defaults. No cloud secrets are required
for Phase 4.

## Development

```bash
pnpm dev            # backend (uvicorn :8000) + frontend (vite :5173)
pnpm dev:backend
pnpm dev:frontend
```

Confirm the API matches this checkout before smoke or acceptance:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live | ConvertTo-Json
git rev-parse HEAD
```

`git_commit` on `/health/live` must match `HEAD`. Mismatched servers fail
smoke/acceptance/E2E reuse checks; unrelated processes are never killed.

## OCR models and visual runtime

```bash
pnpm models:ocr:bootstrap
pnpm models:ocr:verify
pnpm verify:visual-runtime
```

Keep `OCR_WORKERS=1` for the Phase 4 target profile.

## Endpoints

- Health: `GET /health/live` (build identity), `GET /health/ready`
- Sessions: `POST/GET/DELETE /api/v1/sessions/{id}`, `GET .../events` (SSE),
  `POST .../process`
- Documents: upload, cancel, scheduler snapshot, native/visual summaries
- Canonical: `GET .../documents/{doc}/canonical` (range requests, `no-store`)
- `GET http://127.0.0.1:8000/openapi.json`, `/docs`, `/redoc`

## Contracts

```bash
pnpm contracts:generate
pnpm contracts:check
```

Pydantic models under `backend/app/contracts/` are the source of truth.
`docs/contracts/openapi.json` and `frontend/src/contracts/generated/` are
**generated and committed**. See [ADR 0002](docs/decisions/0002-contract-generation.md).

## Smoke corpus

```bash
pnpm smoke:corpus
pnpm smoke:corpus:phase4
pnpm smoke:corpus:critical
pnpm smoke:corpus:validate
```

Requires a ready API whose build identity matches `HEAD`
(`--require-build-identity` defaults on).

## Testing and quality

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm test:ocr
pnpm test:ocr:integration
pnpm evaluate:ocr
pnpm test:e2e
pnpm build
pnpm check
pnpm check:legacy
pnpm check:private
```

Operator detail:
[`docs/operations/phase-4-local-runtime.md`](docs/operations/phase-4-local-runtime.md),
[`docs/operations/phase-4-troubleshooting.md`](docs/operations/phase-4-troubleshooting.md).

## Current limitations

- Phase 4 progress is capped at **65%**. Handwriting, vision LLM, final reading
  order, and final table/form structure are **Phase 5+**.
- Printed OCR remains provisional; `OCR_WORKERS` target profile is **1**.
- Single-process runtime; no database, auth, or demand-letter scope.
- Word conversion fidelity depends on the installed LibreOffice version.

## More documentation

- Phase 4 overview: [`docs/architecture/phase-4-overview.md`](docs/architecture/phase-4-overview.md)
- Final baseline: [`docs/evaluation/phase-4-final-baseline.md`](docs/evaluation/phase-4-final-baseline.md)
- Security review: [`docs/security/phase-4-security-review.md`](docs/security/phase-4-security-review.md)
- Decisions: [`docs/decisions/`](docs/decisions/)
- Dependencies: [`docs/dependencies/`](docs/dependencies/) /
  [`DEPENDENCY_INVENTORY.md`](DEPENDENCY_INVENTORY.md)
- Phase reports: [`docs/phases/`](docs/phases/)

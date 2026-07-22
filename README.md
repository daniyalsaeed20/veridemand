# VeriDemand

VeriDemand is a **document-extraction platform**. It extracts text and structure
from documents using a deterministic pipeline (native text and OCR, with a
vision LLM only for handwritten or uncertain regions). This repository is at the
**Phase 2** stage: runtime sessions, uploads, canonical PDF production, and the
PDF.js viewer with normalised coordinates.

> **Runtime-only product.** VeriDemand keeps uploaded files and results only for
> the duration of a session. Refreshing, closing, or resetting the page may
> permanently remove everything. Nothing is persisted to a database or browser
> storage; a server restart or refresh starts a fresh session.

The sole authoritative specification is
[`docs/SOURCE_OF_TRUTH.md`](docs/SOURCE_OF_TRUTH.md).

## Phase 2 scope

Building on Phase 1, Phase 2 adds:

- **Canonical PDF production** for PDF (byte-identical publish), TXT (deterministic
  ReportLab render), images (Pillow + ReportLab), and Word (LibreOffice headless).
- **Canonical HTTP delivery**: inline PDF with byte ranges, page metadata, and a
  synthetic overlay-proof endpoint.
- **Normalised coordinate contracts** (top-left origin, `[0, 1]`) and rotation
  helpers for viewer alignment.
- **PDF.js viewer** in the frontend with scale controls and synthetic overlay proof.
- Extended **readiness** checks for LibreOffice, ReportLab, and canonical storage.

**No extraction of any kind** is performed in Phase 2: no native-text trust,
OCR, layout analysis, or LLM calls. Documents reach `ready_for_extraction` with
`canonical_view_available: true` but `result_available: false`. See
[`docs/architecture/phase-2-canonical-documents.md`](docs/architecture/phase-2-canonical-documents.md)
and ADRs [0008](docs/decisions/0008-canonical-pdf-policy.md)–[0011](docs/decisions/0011-pdfjs-viewer.md).

### Phase 1 (complete)

Runtime-only sessions, defensive uploads, in-memory queue, SSE progress, and the
upload + queue dashboard. See
[`docs/architecture/phase-1-runtime-sessions.md`](docs/architecture/phase-1-runtime-sessions.md).

### Not implemented yet (later phases)

Native-text trust gate, OCR (PaddleOCR), layout analysis, handwriting routing,
vision-model calls, search, exports, databases, Redis/Celery, and authentication.

## Repository layout

```text
backend/    FastAPI app (installed as an editable package) + tests
frontend/   Vite + React + TypeScript app (pnpm workspace)
docs/       Source of truth, architecture, ADRs, contracts, dependencies, phases
scripts/    Contract generation and cross-platform validation orchestration
models/ fixtures/ temp/   Phase-boundary scaffolding (README-only / gitkeep)
```

## Prerequisites

- **uv** (manages a Python **3.12** environment; the system Python is untouched).
- **Node.js 24.18.0** (`.nvmrc`) with **Corepack** enabled.
- **pnpm 11** (pinned via `packageManager`; `corepack enable pnpm`).
- **LibreOffice** (Writer) for Word canonicalisation and readiness — install
  locally or set `LIBREOFFICE_EXECUTABLE` (see `.env.example`).

## Setup

```bash
uv sync --all-groups
pnpm install
```

Copy `.env.example` to `.env` (root) and `frontend/.env.example` to
`frontend/.env` if you need to override defaults. No secrets are required in
Phase 0.

## Development

```bash
pnpm dev            # backend (uvicorn :8000) + frontend (vite :5173)
pnpm dev:backend
pnpm dev:frontend
```

## Endpoints

- Health: `GET /health/live`, `GET /health/ready` (readiness checks session
  workspace, coordinator, cleanup worker, queue, LibreOffice, ReportLab, and
  canonical storage).
- Sessions: `POST/GET/DELETE /api/v1/sessions/{id}`, `GET .../events` (SSE),
  `POST .../process`.
- Documents: `POST/GET .../documents`, `GET/DELETE .../documents/{doc}`,
  `POST .../documents/{doc}/cancel`.
- Canonical: `GET .../documents/{doc}/canonical`, `GET .../canonical/metadata`,
  `GET .../canonical/overlay-proof`.
- Jobs: `GET .../jobs`, `GET .../jobs/{job}`.
- `GET http://127.0.0.1:8000/openapi.json`, `/docs`, `/redoc`.

## Contracts

```bash
pnpm contracts:generate   # regenerate committed OpenAPI + TS/Zod
pnpm contracts:check      # verify determinism and no drift
```

Pydantic models are the source of truth. `docs/contracts/openapi.json` and
`frontend/src/contracts/generated/` are **generated and committed**; do not edit
them by hand. See [ADR 0002](docs/decisions/0002-contract-generation.md).

## Testing and quality

```bash
pnpm lint          # ruff + eslint
pnpm typecheck     # mypy + tsc
pnpm test          # pytest + vitest
pnpm test:e2e      # Playwright E2E (Chromium)
pnpm build         # frontend production build
pnpm check         # full validation suite (fail-fast)
pnpm check:legacy  # guard against reintroduced legacy scope
```

`pnpm check` runs `scripts/check_all.py`, which validates lockfiles, legacy
scope, contract drift, backend and frontend format/lint/type/test, the frontend
build, the E2E tests, and a residual-session-data guard (use `--skip-e2e` to run
E2E separately). The Playwright E2E starts two backend + dev-server stacks: a
normal one and a "holds" one (test-only admission delay + short TTL) for
cancellation and expiry flows.

## Current limitations

- Single process with exactly one canonicalisation worker; no horizontal scaling.
- No extraction is performed: Phase 2 stops at `ready_for_extraction` with a
  canonical view only.
- Word conversion fidelity depends on the installed LibreOffice version.
- Readiness reports future capabilities as optional `not_configured` (OCR, HTR,
  vision provider).

## More documentation

- Architecture: [`docs/architecture/phase-2-canonical-documents.md`](docs/architecture/phase-2-canonical-documents.md),
  [`docs/architecture/phase-1-runtime-sessions.md`](docs/architecture/phase-1-runtime-sessions.md),
  [`docs/architecture/phase-0-foundation.md`](docs/architecture/phase-0-foundation.md)
- Decisions: [`docs/decisions/`](docs/decisions/)
- Dependencies & licences: [`docs/dependencies/`](docs/dependencies/)
- Phase reports: [`docs/phases/`](docs/phases/)

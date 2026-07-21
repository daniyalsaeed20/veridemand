# VeriDemand

VeriDemand is a **document-extraction platform**. It extracts text and structure
from documents using a deterministic pipeline (native text and OCR, with a
vision LLM only for handwritten or uncertain regions). This repository is at the
**Phase 1** stage: runtime sessions, uploads, and the processing queue skeleton.

> **Runtime-only product.** VeriDemand keeps uploaded files and results only for
> the duration of a session. Refreshing, closing, or resetting the page may
> permanently remove everything. Nothing is persisted to a database or browser
> storage; a server restart or refresh starts a fresh session.

The sole authoritative specification is
[`docs/SOURCE_OF_TRUTH.md`](docs/SOURCE_OF_TRUTH.md).

## Phase 1 scope

Building on the Phase 0 foundation, Phase 1 adds:

- **Runtime-only sessions** created per page load, in-memory with an inactivity
  TTL and guaranteed cleanup (periodic sweep, startup sweep, graceful shutdown).
- **Defensive multi-document uploads**: filename normalisation, extension
  allow-list, streamed size enforcement, magic-byte and MIME checks, and
  format-specific structural validation for PDF, images, DOCX, DOC and TXT — using
  `pypdf`/`Pillow`/`oletools`/`defusedxml` **for validation only**.
- **In-memory processing queue** with a single admission worker and a
  **non-extractive** coordinator that only marks documents `ready_for_extraction`.
- **Live progress over SSE** with stable event ids, bounded replay, resync, and a
  per-session connection cap.
- A responsive **upload + queue dashboard** with reset and expiration UX.

**No extraction of any kind** is performed in Phase 1: no canonicalisation, PDF
rendering, native-text reading, OCR, layout analysis, or LLM calls. See
[`docs/architecture/phase-1-runtime-sessions.md`](docs/architecture/phase-1-runtime-sessions.md)
and ADRs [0004](docs/decisions/0004-runtime-sessions.md)–[0007](docs/decisions/0007-sse-progress-broker.md).

### Not implemented yet (later phases)

Canonicalisation, PDF rendering (`pypdfium2`/MuPDF), OCR (PaddleOCR), layout
analysis, LibreOffice conversion, vision-model calls, handwriting routing,
search, exports, databases, Redis/Celery, and authentication. **Phase 2 has not
been implemented.**

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

- Health: `GET /health/live`, `GET /health/ready` (readiness now also checks the
  session workspace, admission coordinator, cleanup worker, and queue).
- Sessions: `POST/GET/DELETE /api/v1/sessions/{id}`, `GET .../events` (SSE),
  `POST .../process`.
- Documents: `POST/GET .../documents`, `GET/DELETE .../documents/{doc}`,
  `POST .../documents/{doc}/cancel`.
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

- Single process with exactly one queue admission worker; no horizontal scaling.
- No extraction is performed: Phase 1 stops at `ready_for_extraction`.
- Readiness reports future capabilities as optional `not_configured` (see
  [ADR 0003](docs/decisions/0003-phase-0-readiness.md)).

## More documentation

- Architecture: [`docs/architecture/phase-1-runtime-sessions.md`](docs/architecture/phase-1-runtime-sessions.md),
  [`docs/architecture/phase-0-foundation.md`](docs/architecture/phase-0-foundation.md)
- Decisions: [`docs/decisions/`](docs/decisions/)
- Dependencies & licences: [`docs/dependencies/`](docs/dependencies/)
- Phase reports: [`docs/phases/`](docs/phases/)

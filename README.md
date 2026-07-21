# VeriDemand

VeriDemand is a **document-extraction platform**. It extracts text and structure
from documents using a deterministic pipeline (native text and OCR, with a
vision LLM only for handwritten or uncertain regions). This repository is at the
**Phase 0 foundation** stage.

> **Runtime-only product.** VeriDemand keeps uploaded files and results only for
> the duration of a session. Refreshing, closing, or resetting the page may
> permanently remove everything. This principle is visible from the foundation,
> even though sessions themselves arrive in Phase 1.

The sole authoritative specification is
[`docs/SOURCE_OF_TRUTH.md`](docs/SOURCE_OF_TRUTH.md).

## Phase 0 scope

Phase 0 delivers a clean, reproducible foundation:

- pnpm + uv monorepo with pinned runtimes and lockfiles.
- FastAPI backend with a modular application factory.
- Typed, validated environment configuration (`pydantic-settings`).
- Pydantic API contracts, deterministic committed OpenAPI, and generated
  TypeScript + Zod contracts.
- Liveness and readiness endpoints, request-ID middleware, and a canonical error
  envelope.
- React + TypeScript + MUI application shell that calls and validates the
  backend health API.
- Backend and frontend tests, an E2E smoke test, and full quality tooling.

### Not implemented yet (later phases)

Sessions, uploads, queues, SSE, PDF inspection/rendering, OCR (PaddleOCR),
`pdfplumber`/`pypdf`/`pypdfium2`, OpenCV/Pillow, LibreOffice conversion,
DOC/DOCX processing, vision-model calls, handwriting routing, search, exports,
databases, Redis, and authentication. **Phase 1 has not been implemented.**

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

## Health endpoints

- `GET http://127.0.0.1:8000/health/live`
- `GET http://127.0.0.1:8000/health/ready`
- `GET http://127.0.0.1:8000/openapi.json`, `/docs`, `/redoc`

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
pnpm test:e2e      # Playwright smoke test (Chromium)
pnpm build         # frontend production build
pnpm check         # full Phase 0 validation suite (fail-fast)
pnpm check:legacy  # guard against reintroduced legacy scope
```

`pnpm check` runs `scripts/check_all.py`, which validates lockfiles, legacy
scope, contract drift, backend and frontend format/lint/type/test, the frontend
build, and the E2E smoke test (use `--skip-e2e` to run E2E separately).

## Current limitations

- Only health endpoints exist; there is no upload, processing, or extraction.
- Readiness checks only Phase 0 requirements; future capabilities are reported
  as optional `not_configured` (see [ADR 0003](docs/decisions/0003-phase-0-readiness.md)).

## More documentation

- Architecture: [`docs/architecture/phase-0-foundation.md`](docs/architecture/phase-0-foundation.md)
- Decisions: [`docs/decisions/`](docs/decisions/)
- Dependencies & licences: [`docs/dependencies/`](docs/dependencies/)
- Phase reports: [`docs/phases/`](docs/phases/)

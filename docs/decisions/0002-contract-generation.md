# ADR 0002 - Contract generation

- Status: Accepted
- Date: 2026-07-21
- Phase: 0

## Context

The frontend and backend must agree on API shapes without hand-maintaining
duplicate type definitions that silently drift.

## Decision

- **Pydantic models are the source of truth** for API shapes
  (`backend/app/contracts/`). FastAPI derives the OpenAPI document from them.
- **OpenAPI is generated deterministically and committed** to
  `docs/contracts/openapi.json` by `scripts/generate_contracts.py` (in-process,
  no server; recursively sorted keys; 2-space indent; LF; single trailing
  newline; no timestamps, machine paths, or server URLs). Health operations use
  stable operation IDs `health_live` / `health_ready`.
- **TypeScript types and Zod v4 schemas are generated** from the committed
  OpenAPI document by `@hey-api/openapi-ts` (pinned to an exact version) into
  `frontend/src/contracts/generated/`. Generated files are committed and never
  edited by hand. The frontend consumes them via `frontend/src/contracts/index.ts`.
- **Drift fails CI.** `scripts/check_contracts.py` generates twice, compares
  hashes to prove determinism, and runs `git diff --exit-code` on the committed
  contracts. `pnpm contracts:check` runs this and is executed in CI.

## Consequences

- A backend contract change requires regenerating and committing artefacts;
  otherwise the drift check fails.
- The frontend validates responses at runtime with the generated Zod schemas,
  so contract violations surface immediately.

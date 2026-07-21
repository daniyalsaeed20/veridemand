# Phase 0 - Legacy scope removal

The previous demand-letter product was already removed from executable code in
the reset commit `42bc755` ("chore: reset VeriDemand to document extraction
foundation"), which is the base of the Phase 0 branch. This report records the
Phase 0 verification and the additional structural cleanup performed while
normalising the repository to the new foundation layout.

## Audit method

- `git grep -i` for `demand[_ -]*letter`, `legal[_ -]*workflow`, `chronology`,
  `settlement`, `contradiction`, `billing`, `claim valuation`,
  `draft/demand generation`, `docx generator`, `case facts`,
  `medical analysis`, `legal review`, `letter template`.
- Automated guard `scripts/check_no_legacy_scope.py` over `backend/`,
  `frontend/src/`, and `scripts/`.

## Findings

- **No demand-letter executable code exists** in `backend/`, `frontend/src/`, or
  `scripts/`. The automated guard exits 0.
- The only remaining references to legacy concepts are **documentation of
  exclusions**: `docs/SOURCE_OF_TRUTH.md`, this report, and the Cursor rule
  `.cursor/rules/veridemand-source-of-truth.mdc` (which lists the out-of-scope
  legacy product). These are intentionally allowed and are not executable code.

## Removed in this phase (structural cleanup / superseded artefacts)

Removed via `git rm` (history retains them):

- `backend/pyproject.toml`, `backend/uv.lock` - replaced by root-level uv project.
- `backend/README.md`, `backend/.env.example` - superseded by root docs/`.env.example`.
- `backend/app/core/` (`errors.py`, `logging.py`, `middleware.py`,
  `server_settings.py`) - replaced by `settings/` + `observability/`.
- `backend/app/models/` (`enums.py`, `error_envelope.py`, `health.py`,
  `registry.py`, `taxonomies.py`) - replaced by `contracts/`.
- `backend/app/services/health.py` - replaced by `health/service.py`.
- `backend/app/api/v1/health.py` - replaced by `api/v1/endpoints/health.py`
  (mounted at root).
- `backend/tests/**` (old unit/integration tests) - replaced by the new suite.
- `contracts/generated/**` (old json-schema-to-zod output) - replaced by
  `docs/contracts/openapi.json` + `frontend/src/contracts/generated/`.
- `scripts/check-all.mjs`, `scripts/check-contracts.mjs`,
  `scripts/generate-zod.mjs`, `scripts/proof-drift-fails.mjs`,
  `scripts/generate_json_schemas.py` - replaced by the Python contract/orchestration scripts.
- `scripts/build_extraction_fixtures.py` - later-phase tooling out of Phase 0 scope.
- `frontend/src/**` (old `api/client.ts`, `schemas/**`, `fixtures/**`,
  `app/App.tsx`, etc.), `frontend/package-lock.json` (npm),
  `frontend/eslint.config.js`, `frontend/index.html`, `frontend/tsconfig.json`,
  `frontend/vite.config.ts`, `frontend/.prettierrc.json` - rebuilt for the new
  pnpm + MUI + TanStack Query + generated-contracts frontend.
- `DEPENDENCY_INVENTORY.md` (root) - replaced by `docs/dependencies/`.

Removed local (gitignored) artefacts:

- `backend/.venv/` and `frontend/node_modules/` (npm) - stale local installs.

## Removed routes / endpoints

- No demand-letter API routes existed to remove. The single legacy `/health`
  endpoint and its `contracts_version`/registry machinery were replaced by the
  canonical `/health/live` and `/health/ready` endpoints.

## Removed dependencies

- No demand-letter-only production dependencies existed in the reset base. The
  frontend was migrated from npm to pnpm and its dependency set was rebuilt to
  the Phase 0 list (no upload/PDF/SSE/drag-drop libraries).

## Preserved extraction fixtures

- `fixtures/extraction_acceptance/**` - synthetic acceptance PDFs retained for
  future extraction regression testing (no legal/demand-letter value removed).
- `docs/example/**` local case documents remain **gitignored** (possible PII);
  they are not part of version control.
- `docs/roadmap.md` retained.

## Ambiguous items

- `.cursor/rules/veridemand-source-of-truth.mdc` mentions legacy terms only to
  forbid them; preserved intentionally as project guidance.

## Final search result

`python scripts/check_no_legacy_scope.py` -> `OK: no legacy demand-letter scope
found in active code.`

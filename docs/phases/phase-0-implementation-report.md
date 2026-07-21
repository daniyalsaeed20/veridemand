# Phase 0 - Implementation report

- Date: 2026-07-21
- Branch: `phase/0-repository-foundation-contracts`
- Starting commit: `42bc755` ("chore: reset VeriDemand to document extraction foundation")
- Ending commit: the final `docs(phase-0)` commit on this branch (see `git log`).
- Tag: `phase-0-foundation-v1` (annotated, created after all gates passed).

## Runtime versions

| Tool | Version | Notes |
|---|---|---|
| uv | 0.11.30 | Installed via pip (`--user`); winget/Astral installer unavailable on host |
| Python (project) | 3.12.13 | uv-managed; `.python-version` pins `3.12` |
| Python (system) | 3.13.14 | Untouched; global `python` unchanged |
| Node.js | 24.18.0 | Pre-installed; `.nvmrc` = 24.18.0 |
| pnpm | 11.15.1 | Corepack; pinned in `packageManager` |

## New architecture

Root-level uv Python project (`backend` installed as editable package) plus a
pnpm workspace for `frontend`. FastAPI application factory `create_app()` with
request-ID middleware, canonical error envelope, and health routes
(`/health/live`, `/health/ready`) mounted at the root; an empty `/api/v1`
router reserved for later phases. Pydantic contracts are the source of truth;
OpenAPI is generated deterministically and committed; the frontend consumes
generated TypeScript + Zod. See `docs/architecture/phase-0-foundation.md`.

## Files and modules removed

See `docs/phases/phase-0-legacy-removal.md`. No demand-letter executable code
existed at the reset base; structural cleanup removed the old backend layout,
the previous json-schema contract pipeline, the npm frontend, and the root
dependency inventory.

## Direct dependency versions

See `docs/dependencies/direct-dependencies.md` (exact locked versions and
licences; Python licences confirmed from installed metadata). No OCR, PDF,
imaging, MuPDF/HTR, vision-model, database, or queue dependency was added.

## Health responses (real HTTP, via `pnpm dev`)

`GET /health/live` -> `200`, header `X-Request-ID` equals body `request_id`:

```json
{"status":"ok","service":"veridemand-api","app_name":"VeriDemand","version":"0.1.0","timestamp":"2026-07-21T20:09:01.925951Z","request_id":"83374cf273104fb0822f1ab6c23724ab"}
```

`GET /health/ready` -> `200`, `status: "ready"`, required checks pass, future
dependencies reported `not_configured`:

```json
{"status":"ready","service":"veridemand-api","app_name":"VeriDemand","version":"0.1.0","checks":[{"name":"settings","status":"pass","required":true},{"name":"temp_storage","status":"pass","required":true},{"name":"libreoffice","status":"not_configured","required":false},{"name":"paddle_ocr","status":"not_configured","required":false},{"name":"handwriting_classifier","status":"not_configured","required":false},{"name":"openai_vision","status":"not_configured","required":false}]}
```

`GET /openapi.json` -> `200`; `GET /docs` -> `200`; frontend `http://localhost:5173` -> `200`.

## Contract hashes (SHA-256)

```text
e7de69aa37bd92091b50fa808a5c5a20df85198e6da704e55ac1c07fc0b24b4b  docs/contracts/openapi.json
ed9646844fd1f8f4691c8c002079f883bf4267dd9e64562d3588ce178ba02768  frontend/src/contracts/generated/types.gen.ts
8b33f795f9cb0cd2aa9036473a2c60daf9b2c93833a99d826e5e37057dcada61  frontend/src/contracts/generated/zod.gen.ts
993ac28a5275e2df77cf404e822e1c7325c8fa13e158ce6e5bdc768f001c5454  frontend/src/contracts/generated/index.ts
```

## Commands run (all succeeded)

- `uv sync --all-groups`, `uv run python --version` (3.12.13)
- `pnpm install`
- `pnpm contracts:generate`, `pnpm contracts:check`
- `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build`, `pnpm test:e2e`
- `pnpm check` (full suite, incl. lockfile checks, legacy scan, contract
  determinism, and E2E) -> "All Phase 0 validation steps passed."
- `python scripts/check_no_legacy_scope.py` -> OK

## Test counts

- Backend (pytest): **24 passed**.
- Frontend (vitest): **6 passed** (2 files).
- E2E (Playwright, Chromium): **1 passed**.

## Build outcome

`vite build` succeeded (`dist/index.html` + one JS chunk ~464 kB / ~142 kB
gzip). No secrets or backend-only terms present in the built assets.

## E2E outcome

Application loads, backend reports Live and Ready, no console errors, no failed
health requests.

## Contract determinism evidence

`scripts/check_contracts.py` generated the contracts twice with identical hashes
(above) and `git diff --exit-code` on the committed contracts was clean.

## Legacy-scope scan outcome

`OK: no legacy demand-letter scope found in active code.`

## Known limitations

- Only health endpoints exist; no Phase 1+ functionality.
- Readiness checks only Phase 0 requirements (ADR 0003).
- The `starlette.testclient` emits an httpx deprecation warning (cosmetic).

## Deviations from the prompt

- Node baseline changed from Node 22 to **Node 24.18.0** (approved). Python
  remains 3.12, supplied by uv; system Python 3.13 remains and the global
  `python` is unchanged.
- `uv` installed via `pip --user` because `winget` and the Astral PowerShell
  installer were unavailable on the host; the uv scripts directory was added to
  the user PATH.
- `scripts/__init__.py` was added (not in the prompt tree) so `scripts` is a
  proper package, giving deterministic module resolution for mypy and the
  OpenAPI test.
- Health route handlers live in `backend/app/api/v1/endpoints/health.py` (per the
  prescribed tree) but are mounted at the application root, outside `/api/v1`,
  to satisfy the canonical URL contract.

## Push status

All six commits and the annotated tag `phase-0-foundation-v1` exist locally on
`phase/0-repository-foundation-contracts`. The push to `origin`
(`daniyalsaeed20/veridemand`) is **blocked**: the available GitHub tokens (git
credential and `gh`) only have the `repo` scope, and GitHub refuses to accept a
commit that adds `.github/workflows/ci.yml` without the `workflow` scope. To
finish: grant the scope (`gh auth refresh -s workflow`) or use a PAT with
`workflow`, then `git push -u origin phase/0-repository-foundation-contracts`
and `git push origin phase-0-foundation-v1`. The branch was not merged.

## Phase boundary confirmation

No Phase 1 endpoint, upload, queue, extraction library, OCR/LLM integration,
database, or authentication exists. Phase 1 was not started.

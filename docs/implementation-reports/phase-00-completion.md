# Phase 0 Completion Report — Repository and Contracts

**Date:** 2026-07-19  
**Module:** [00-repository-and-contracts.md](../modules/00-repository-and-contracts.md)  
**Acceptance matrix:** [phase-acceptance-matrix.md](../readiness/phase-acceptance-matrix.md) Phase 0  

## Closure identifiers

| Item | Value |
|------|-------|
| Final Phase 0 commit | `7dbcf321fe5ae4d2aed11aa587576421603bb707` (pre-amend; updated after closure evidence amend) |
| Tag | `phase-00-pass` |

## Baseline preservation

| Item | Value |
|------|-------|
| Readiness baseline commit (pre-application scaffold) | `692dd0cb3dcbee890178eeec7b95f147d06901a2` — *Initial commit: docs, contracts, spikes, and Cursor project rules.* |
| Hygiene commit before scaffold | `00e3cd0625de5a85f4105cbc6cda5628717ccf8b` — expanded `.gitignore` |
| Readiness spike evidence | Unmodified (`docs/readiness/*`, `spikes/**` sources retained; `out/` gitignored) |
| Canonical doctrine / contracts Markdown | Additive `route_not_found` only; no silent requirement changes |

## Scope implemented

- Monorepo layout at repo root: `frontend/`, `backend/`, `contracts/generated/`, `fixtures/`, `scripts/`, `templates/`, backend service package stubs
- FastAPI app with `/api/v1/health`, AppSettings from environment, CORS, request IDs, structured logging + masking, error envelope, global handlers
- Full Pydantic contract pack from `docs/contracts/` (entities, enums, fact/issue taxonomies, error codes)
- JSON Schema export + Zod generation (`json-schema-to-zod`) + drift check
- React/Vite/TypeScript strict shell validating health via Zod
- Backend/frontend quality tooling and one-command gate `node scripts/check-all.mjs`
- Dependency inventory with OCR Phase 3 pin recorded (not installed)
- Golden harness scaffold (metadata only)
- Phase 0 closure: formal `route_not_found` in contracts + clean-env verification

**Not implemented (by design):** sessions, upload, OCR, classification, billing, drafting, export, database.

## Requirement IDs addressed

| Mapping | Evidence |
|---------|----------|
| §6.2 stack | React/Vite/TS + Zustand/Zod; FastAPI + Pydantic; no paid DocAI |
| §7.1–7.3 | Evidence entity models; opaque IDs; normalized polygons `[0,1]` |
| §14.1 | `/api/v1` routes; Pydantic responses; no local paths in health |
| Appendix D | `AppSettings` defaults + env overrides |
| Module 00 exit | API starts; contracts validate; health; unit/integration/golden scaffold |
| OD-02 / OD-03 | Resolved — see open-decisions status rows |

## Architecture decisions

1. **Layout:** Appendix C packages at **repo root** (not nested under `prototype/`).
2. **Contracts:** Markdown human SoT → Pydantic machine SoT → JSON Schema → generated Zod; commit generated artifacts.
3. **Generator:** `json-schema-to-zod@2.6.1`.
4. **Readiness endpoint:** No separate `/ready`; process boots only with valid settings; health is the contracted probe.
5. **CORS / LOG_LEVEL / APP_VERSION:** Server bootstrap env, **outside** contracted `AppSettings` fields.
6. **Health `ocr_enabled`:** `false` in Phase 0 (OCR not in app).
7. **Python tooling:** `pyproject.toml` + `uv.lock` via `python -m uv` (uv installed into `.tools` tooling).
8. **Unknown routes:** HTTP 404 with contracted `error_code: route_not_found` (distinct from domain `*_not_found` codes).

## Files created or modified (high level)

- `backend/` — FastAPI app, models, tests, `pyproject.toml`, `uv.lock`
- `frontend/` — Vite React app, generated schemas, lockfile
- `contracts/generated/` — exported JSON Schema
- `scripts/` — generate/check/proof/check-all
- `fixtures/health-ok.json`, `docs/local-setup.md`, `DEPENDENCY_INVENTORY.md`
- `.gitignore`, `.nvmrc`
- `docs/contracts/error-codes.md` / `README.md` — `route_not_found`
- `docs/readiness/open-decisions.md` — OD-02/OD-03 status
- This report

## Dependencies

See [DEPENDENCY_INVENTORY.md](../../DEPENDENCY_INVENTORY.md).  
**Phase 3 OCR constraint (not installed):** PaddleOCR **2.7.3** + PaddlePaddle **2.6.2**.

## Commands used

```text
backend\.venv\Scripts\python.exe -m ruff format --check app tests
backend\.venv\Scripts\python.exe -m ruff check app tests
backend\.venv\Scripts\python.exe -m mypy app
backend\.venv\Scripts\python.exe -m pytest -q
backend\.venv\Scripts\python.exe scripts\generate_json_schemas.py
node scripts\generate-zod.mjs
node scripts\check-contracts.mjs
node scripts\proof-drift-fails.mjs
cd frontend && npm run format:check && npm run lint && npm run typecheck && npm test && npm run build
node scripts\check-all.mjs
```

## Deterministic contract generation

Commands:

```text
Remove-Item -Recurse -Force contracts\generated\*
Remove-Item -Recurse -Force frontend\src\schemas\generated\*
backend\.venv\Scripts\python.exe scripts\generate_json_schemas.py
node scripts\generate-zod.mjs
backend\.venv\Scripts\python.exe scripts\generate_json_schemas.py
node scripts\generate-zod.mjs
node scripts\check-contracts.mjs
```

**Result:** Second regeneration produced no content change vs the first (`contracts:check OK — no drift`). Artifact counts: 24 JSON Schema files (incl. `index.json`), 24 Zod modules (incl. `index.ts`).

## Test results

| Suite | Result |
|-------|--------|
| Backend pytest | **21 passed** |
| Frontend vitest | **2 passed** |
| Contract drift proof | **OK** (tamper detected) |
| `node scripts/check-all.mjs` | **All Phase 0 checks passed** |

Proven behaviours:

- App boots; `GET /api/v1/health` matches `HealthResponse`
- Unknown route → `route_not_found` envelope + `request_id` / `X-Request-ID`
- Sensitive log values masked (`SUPER_SECRET_VALUE_XYZ` not present in formatted logs)
- Schema export succeeds; FE Zod regenerated from backend schema; intentional drift fails check
- Frontend production build succeeds; Zod validates synthetic health fixture
- Invalid AppSettings env raises `ConfigurationError` with safe message
- Temp/example binaries / spike `out/` not tracked (hygiene tests)

## Build results

- Frontend `vite build`: success (`dist/` produced)
- Backend package editable install: success
- mypy: success (48 source files)
- ruff check: success

## Contract generation process

1. Implement/edit Pydantic models under `backend/app/models/`
2. `python scripts/generate_json_schemas.py` → `contracts/generated/*.schema.json`
3. `node scripts/generate-zod.mjs` → `frontend/src/schemas/generated/*.ts`
4. `node scripts/check-contracts.mjs` fails if regeneration would change committed artifacts

Frontend health wire validation: generated `HealthResponseSchema` plus a narrow `.and(...)` object in `frontend/src/schemas/health.ts` because `json-schema-to-zod` currently emits `z.any()` for some enum/$ref shapes. Field authority remains Pydantic/JSON Schema; the overlay does not invent alternate field names.

## Specification conflicts / gaps

| ID | Description | Handling |
|----|-------------|----------|
| SC-04 | Module 00 still mentions hand-maintained Zod; readiness requires generation | Followed readiness **B**; recorded OD-02 resolved |
| Gap (closed) | Generic HTTP 404 route code | Added contracted `route_not_found` to `error-codes.md` (v0.1 additive); regenerated schemas/Zod |
| Note | Appendix C `prototype/` prefix vs repo root | Documented ADR; layout at root |

No silent doctrine changes.

## Repository safety (pre-commit)

| Category | Result |
|----------|--------|
| `.env` / credentials (excl. `.env.example`) | PASS — none staged |
| Python virtualenvs (`.venv`) | PASS — none staged |
| `node_modules` | PASS — none staged |
| Temp/runtime/session dirs | PASS — none staged |
| OCR models / paddle weights | PASS — none staged |
| Real case PDF/DOCX | PASS — none staged |
| Confidential generated docs | PASS — none staged |
| Machine-specific absolute paths in staged generated/lock JSON | PASS — none found |

Staged file count at inspection: **140**.

## Clean-environment verification

Worktree: `D:\Applications\VeriDemand-phase0-verify` at tag `phase-00-pass` (commit `7dbcf32`).

| Step | Command | Result |
|------|---------|--------|
| Backend venv | `uv venv backend/.venv --python 3.12.8` | OK |
| Backend sync | `uv sync --frozen --extra dev --directory backend` | OK (lock not updated) |
| Backend pytest | `python -m pytest -q` | **21 passed** |
| Backend ruff | `python -m ruff check app tests` | All checks passed |
| Backend mypy | `python -m mypy app` | Success (48 files) |
| Frontend install | `npm ci` | OK |
| Frontend tests | `npm test` | **2 passed** |
| Frontend typecheck | `npm run typecheck` | OK |
| Frontend build | `npm run build` | OK |
| Contract generate | `generate_json_schemas.py` + `generate-zod.mjs` | OK |
| Contract drift | `check-contracts.mjs` | **OK — no drift** |
| One-command gate | `node scripts/check-all.mjs` | Failed once on `prettier --check` due to CRLF checkout vs LF-formatted tree |

**Remediation included in Phase 0 closure commit:** `frontend/.prettierrc.json` `endOfLine: "auto"`, ignore `package-lock.json` in Prettier, add `.gitattributes` (`eol=lf`). Re-verified after amend/retag.

## Known limitations (nonblocking)

- Generated Zod is looser than Pydantic for some enums (`z.any()`); health overlay compensates for Phase 0 wire path
- No GitHub Actions workflow file yet (one-command local gate exists)
- `docs/example` binaries remain local-only (gitignored)
- Separate Kubernetes-style `/ready` not provided (by design)

## Deferred work

Phase 1+: sessions, upload, viewer, OCR (with pinned stack), classification, facts, billing, issues, drafting, export, evaluation.

## Security observations

- CORS restricted to configured origins
- Health omits paths/secrets/session/document text
- Structured logs mask sensitive keys; `LOG_DOCUMENT_TEXT` default false
- Example case PDFs/DOCX excluded from Git
- No document-processing endpoints exposed

## Exit-gate evidence

| Gate criterion | Evidence |
|----------------|----------|
| Schemas compile | Pydantic models + JSON Schema export + mypy/pytest contract tests |
| FE/BE validated health | Integration test + FE Zod fixture test + shell fetch path |
| Tests run with one command | `node scripts/check-all.mjs` green |
| OD-02 parity | Generator + drift check + proof script |
| Closure | `route_not_found` contracted; clean lockfile install verified |

## Final verdict

# PASS

_(confirmed after clean-environment verification)_

Phase 1 was not started.

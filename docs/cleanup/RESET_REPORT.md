# Reset Report — Document-Extraction Foundation

Date: 2026-07-21
Branch: `cleanup/reset-document-extraction`
Base / original HEAD: `31178d964005efed3650c9f3372f1af5985736bd`
Archive branch: `archive/pre-document-extraction-reset-20260721` @ `31178d9`
Canonical specification (preserved verbatim, now committed):
`docs/VeriDemand_Document_Extraction_Source_of_Truth_v1.0.md`

This reset transitions VeriDemand from the obsolete demand-letter product to a minimal,
runnable document-extraction **foundation shell**. No extraction features were implemented.

## Safety process (preconditions confirmed before changes)

1. Recorded git state: dirty tree (8 modified tracked + untracked bake-off/remediation
   leftovers + untracked canonical spec) on `remediation-02-extraction-bakeoff` @ `31178d9`.
2. Created archive branch `archive/pre-document-extraction-reset-20260721` at `31178d9`.
3. Switched to new branch `cleanup/reset-document-extraction` from `31178d9`.
4. Discarded the uncommitted bake-off/remediation work (restored 8 modified tracked files,
   deleted untracked leftovers). Kept only the untracked canonical spec.
5. Re-verified: working tree clean except the intentionally untracked spec; spec path exact;
   archive at `31178d9`; cleanup branch active. No unexpected user work present.

## `.gitignore` and private fixtures (request steps 1 & 6)

Added to `.gitignore`:

```
fixtures/private/*
!fixtures/private/README.example.md
```

Verification results:

- `git check-ignore -v fixtures/private/test-private-document.pdf` →
  `.gitignore:54:fixtures/private/*  fixtures/private/test-private-document.pdf` (ignored).
- `git check-ignore -v fixtures/private/README.example.md` → no match, exit 1 (**trackable**).
- Temporary `fixtures/private/test-private-document.pdf` showed `!!` (ignored) under
  `git status --short --ignored`, then was removed.
- `git ls-files fixtures/private` → only `fixtures/private/README.example.md`.
- No real private document is tracked; none was invented, copied, or moved.

`fixtures/private/README.example.md` lists expected local regression **categories/filenames**
only (native-text PDF, corrupt text-layer PDF, long scanned printed PDF, image-only scan,
mixed printed/handwritten form, handwritten page, rotated/skewed scan, table-heavy document,
single-page image) with no confidential content.

## Synthetic fixtures (request step 2)

- **Preserved: 0** (every original `ground_truth.json` carried old-harness/legal metadata).
- **Rebuilt minimally: 15** — synthetic PDF/PNG bytes kept; ground truth rewritten to
  extraction-only concepts (pages, blocks, lines, words, tables/cells, normalized top-left
  `[0,1]` coordinates, source modes, script types, recognition methods, warnings). Dropped
  `annotation_status`, `expected_outcome` review states, `native_trustworthy`,
  `must_reject_corrupt`, `silent_mix`, and all legal `critical_fields`.
- **Removed: 2** — `person_name_field`, `law_firm_name_field` (sole purpose was excluded
  critical-fact/legal-field extraction + verification).
- Rebuilt fixtures are documented as **future gold inputs with no active test**; no extraction
  engine was built to satisfy them. `MANIFEST.json` and `README.md` were updated; the rebuilt
  builder lives at the domain-neutral path `scripts/build_extraction_fixtures.py`.
- Residue scan of `fixtures/extraction_acceptance/` for old-harness/legal keys: none found.

## CI and Docker (request step 3)

No CI or Docker configuration existed before the reset (no `.github/`, `Dockerfile`, or
compose file). None was added during the cleanup. All validation was run locally.

## Cleanup decision (request step 5)

Preserved only: the canonical spec; domain-neutral infrastructure (logging, request-id
middleware, error envelope, server settings); codegen/drift tooling; the minimal FastAPI +
React health shell; the rebuilt synthetic fixtures; cleanup/decision records; and the new
Cursor rule. Deleted the obsolete demand-letter implementation, docs, contracts, modules,
readiness, reports, examples, remediation, spikes, templates, and old Cursor rules. See
`docs/cleanup/LEGACY_REMOVAL_AUDIT.md` for the full REMOVE/PRESERVE/REBUILD classification.

No uploads, queues, sessions, OCR, rendering, handwriting classification, LLM calls, SSE,
document viewer, or extraction features were implemented.

## Local validation results (request step 7)

All commands run via `node scripts/check-all.mjs` (plus targeted checks). Exact results:

| Check | Command | Result |
|-------|---------|--------|
| Backend format | `ruff format --check app tests` | 22 files already formatted |
| Backend lint | `ruff check app tests` | All checks passed |
| Backend types | `mypy app` | Success: no issues in 18 source files |
| Backend tests | `pytest -q` | 13 passed |
| Backend import | `python -c "import app.main"` | import app.main OK |
| JSON Schema gen | `generate_json_schemas.py` | exported 2 schemas (HealthResponse, ErrorEnvelope) |
| Zod gen | `generate-zod.mjs` | generated 2 Zod modules |
| Contract drift | `check-contracts.mjs` | contracts:check OK — no drift |
| Drift proof | `proof-drift-fails.mjs` | drift-check proof OK (tamper detected) |
| Frontend format | `npm run format:check` | All matched files use Prettier code style |
| Frontend lint | `npm run lint` | clean (eslint, no errors) |
| Frontend types | `npm run typecheck` | clean (tsc --noEmit) |
| Frontend tests | `npm test` | 2 passed |
| Frontend build | `npm run build` | built OK (tsc + vite) |
| Dependency lock | `uv lock` + `uv sync --extra dev` | 33 packages resolved; 82 stale packages removed |
| Frontend lock | `npm install` | package-lock refreshed (pdfjs-dist, zustand removed) |

Additional checks:

- Forbidden-residual scan (case-insensitive) for old concepts (`demand`, `chronology`,
  `settlement`, `preflight`, `contradiction`, `billing`, `timeline`, `drafting`,
  `verification`, and whole-word `fact`/`issue`/`draft`) across tracked files, excluding the
  canonical spec, `0001-reset-...md`, `docs/cleanup/*`, and the new Cursor rule: **only the
  brand name "VeriDemand" matched (substring "demand")**; no domain-concept residue.
- Canonical spec unchanged (added verbatim; not edited).
- Archive branch still at `31178d9`.
- No secrets or private fixtures staged; `contracts/generated` contains only Health +
  ErrorEnvelope; no `.venv`/`node_modules`/`.tools` staged.
- `git diff --cached --check`: the only flags are intentional Markdown hard-line-break
  trailing spaces inside the canonical specification, which is preserved verbatim per the
  source-of-truth rule and was not modified.

## Phase boundary reached

The repository is at the **foundation shell**: health endpoints only, contracts trimmed to
Health + ErrorEnvelope, generated schemas in sync, synthetic fixtures staged as future gold
inputs. No roadmap extraction phase has been started. Feature work (upload, render, native
extraction and trust gate, detection, routing, OCR, vision-LLM transcription) is deferred to
subsequent, separately gated phases.

## Cleanup commit

- Commit message: `chore: reset VeriDemand to document extraction foundation`
- Commit: the single `HEAD` of branch `cleanup/reset-document-extraction` (this report is part
  of that commit; resolve the exact hash with `git rev-parse HEAD`).
- No push, no tag.

The reset landed as one verified commit on `cleanup/reset-document-extraction`.

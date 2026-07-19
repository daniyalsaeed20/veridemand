# Phase 1 Hardening Report — Audit Gap Closure

**Date:** 2026-07-19  
**Branch:** `phase-01-audit-hardening`  
**Baseline:** `phase-01-pass` → `1d9c6127a555995d312daf8e051205bfc664a5dd`  
**Audit:** [phase-01-audit.md](./phase-01-audit.md) (PASS WITH GAPS)

## Audit findings addressed

| Audit ID | Finding | Resolution |
|----------|---------|------------|
| S-01 | Session/document mutation outside lock during ingest | Prepare → validate (off lock) → `commit_upload` (locked); document delete owned by `SessionService` |
| S-02 | Absolute / unsafe DOCX ZIP member names accepted | `assert_safe_zip_member_name` rejects POSIX/Windows absolute, UNC, drive, `..`, null bytes |
| S-03 | Macro-bearing `.docx` (`vbaProject.bin`) accepted | Reject macros via entries, Content_Types, and relationships → `upload_macros_not_supported` |
| D-01 | OD-05 “explicit error” vs accept-without-convert | Matrix + OD-05 clarified: Phase 1 stores DOCX as `uploaded`; conversion is Phase 2 |
| D-02 | Amini reference not in Phase 1 CI | Documented in matrix + local-setup: local gitignored package for Phase 2/3 only |

## Implementation approach

### Concurrency

- `SessionService.prepare_upload` — locked live-session check; returns `uploads_dir` + `generation`
- Off-lock stream + signature/MIME/inspect/hash to provisional then stable internal name
- `SessionService.commit_upload` — `before_commit` hook **outside** lock (no deadlock); then locked re-check generation/expiry/quotas/hash_index; atomic register
- Session delete/expire bumps `generation` and removes workspace (including provisionals)
- Failed commit leaves provisional cleanup to `DocumentService` `finally`

### DOCX security

- Unsafe member names → `upload_corrupt_file` (no path leakage)
- Macros → `upload_macros_not_supported` (catalogue + Pydantic `ErrorCode`; contracts_version remains **0.1**)
- Validation uses `ZipFile` metadata/`read` only — no extract to session disk

### Docs / UI

- OD-05 and Phase 1 acceptance matrix updated
- Local Amini assignment documented
- UI shows “Awaiting normalization” for `status === uploaded`

## Tests added

| File | Coverage |
|------|----------|
| `backend/tests/unit/test_upload_races.py` | Delete race, expiry race, file-count race, total-size race, concurrent identical SHA, lost registration cleanup |
| `backend/tests/unit/test_docx_security.py` | Unsafe path matrix, VBA entry/content-type/relationship, renamed docm |
| `backend/tests/integration/test_sessions.py` | Macro + unsafe ZIP upload API; no residual files |

## Exact test results (2026-07-19)

| Suite | Result |
|-------|--------|
| Backend pytest | **83 passed** |
| Backend ruff format/check | PASS |
| Backend mypy | PASS |
| Frontend vitest | **6 passed** |
| Frontend typecheck / lint / build | PASS |
| Contract drift + proof-drift-fails | PASS |
| `node scripts/check-all.mjs` | **All Phase 1 checks passed** |

## Contract / documentation changes

- `docs/contracts/error-codes.md` — additive `upload_macros_not_supported`
- `ErrorCode` + `ERROR_MESSAGES` updated
- `docs/readiness/open-decisions.md` OD-05 clarified
- `docs/readiness/phase-acceptance-matrix.md` Phase 1 rows clarified
- `docs/local-setup.md` — Amini local fixture assignment
- `docs/implementation-reports/phase-01-completion.md` — hardening pointer
- `contracts_version` remains **0.1**

## Race-condition evidence

Barrier-driven tests (no sleep-only): concurrent committers sync on `before_commit`; peer deletes/expires or competes for quotas. Outcomes assert contracted errors, single winner for limits, deterministic duplicate pair, empty registry/workspace after lost registration.

## DOCX security evidence

Unit matrix rejects absolute/UNC/drive/`..`/null names without extraction. Macro packages rejected with user-safe `upload_macros_not_supported`. Integration confirms empty `uploads/` and empty document list after reject.

## Remaining limitations

- FR-UPL-06 / FR-UPL-07 still Phase 2 (by design)
- Opaque session ID remains the only capability (prototype auth model)
- Periodic sweeper tick still not interval-asserted beyond lifespan shutdown + callable cleanup
- Generated Zod enum looseness (`z.any()`) unchanged

## Tagging

- **`phase-01-pass` was not moved or deleted**
- **`phase-01-audited-pass` not created** — awaits a fresh independent audit PASS on this branch

## Final verdict

# HARDENING COMPLETE

Material audit gaps S-01/S-02/S-03 and documentation gaps D-01/D-02 are closed with automated evidence. Ready for independent re-audit before `phase-01-audited-pass`.

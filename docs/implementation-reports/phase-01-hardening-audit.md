# Phase 1 Hardening Re-Audit — Independent Verification

**Audit date:** 2026-07-19  
**Auditor:** Fresh independent verification of hardening (not the hardening author’s PASS claim)  
**Method:** Clean detached worktree at the hardening commit + lockfile-only dependency sync + code inspection + barrier-based race reproduction + adversarial probes + full quality gate  

**Constraints honored:** No production code changes. No Phase 2 work. No Git tag create/move/delete.

## Audited branch and commit

| Item | Value |
|------|-------|
| Branch | `phase-01-audit-hardening` |
| **Hardening commit** | `5ab566ff7ad63e51ee8a08f2c7b5ebb6bccec093` |
| Commit subject | `phase-01: harden session races and DOCX package security` |
| Working tree audited | Detached worktree `D:\Applications\VeriDemand-phase01-hardening-audit` at exact `5ab566f` (clean) |
| Primary checkout | Also confirmed `HEAD == 5ab566f` on `phase-01-audit-hardening` |

### Tag immutability

| Tag | Annotated object | Peeled commit | Status |
|-----|------------------|---------------|--------|
| `phase-01-pass` | `eed0412b185c1ef45982a549e05ad5c17b38f23d` | `1d9c6127a555995d312daf8e051205bfc664a5dd` | **Unchanged** |
| `phase-00-pass` | `0f1e195489774889374c41d05333f324816d5bea` | `aad013cb56b3c366583761f8eab51b03876e4a24` | **Unchanged** |

`1d9c612` is an ancestor of `5ab566f`. Tag `phase-01-audited-pass` was **not** created by this audit.

## Previous findings reviewed

Source: [phase-01-audit.md](./phase-01-audit.md) (PASS WITH GAPS) and claimed closures in [phase-01-hardening.md](./phase-01-hardening.md).

| Prior ID | Finding | Hardening claim | Re-audit result |
|----------|---------|-----------------|-----------------|
| S-01 | Ingest mutated session state outside lock; no race tests | prepare → off-lock validate → locked `commit_upload`; race suite | **Closed** |
| S-02 | Absolute/unsafe DOCX ZIP member names accepted | `assert_safe_zip_member_name` | **Closed** |
| S-03 | Macro-bearing `.docx` accepted | Macro entry / Content_Types / relationships → `upload_macros_not_supported` | **Closed** |
| D-01 | OD-05 “explicit error” vs accept-without-convert | Matrix + OD-05 + completion wording aligned to option C / Phase 2 conversion | **Closed** |
| D-02 | Amini reference not in Phase 1 CI | Matrix + local-setup: synthetic CI; Amini local/gitignored for Phase 2/3 | **Closed** |

Non-material leftovers from the prior audit (sweeper interval assertion, Zod `z.any()` looseness, module Status markers, opaque-session auth model) remain as **nonblocking observations** and were not claimed closed by hardening.

## Diff scope reviewed

```text
phase-01-pass..5ab566f
# 18 files, +1314 / −165
```

Commits in range: 1 (`5ab566f` hardening only).

```text
phase-00-pass..5ab566f
# 50 files, +4234 / −38
```

Commits in range: 3 (Phase 1 implement + completion hash + hardening).

**Touched areas:** session/document services; DOCX validation; domain error catalogue; unit/integration tests + fixtures; OD-05 / acceptance matrix / local-setup / completion pointer; FE “Awaiting normalization” UI; audit + hardening reports.

**Scope-drift scan:** No OCR, PaddleOCR, pdfplumber, PDF.js, LibreOffice conversion, classification, chronology, billing, LLM, drafting, export, or thumbnail-generation dependencies/routes in either diff. `backend/pyproject.toml` / `frontend/package.json` contain no Phase 2 extraction/viewer/LLM packages.

## Code paths inspected

| Path | Role |
|------|------|
| `backend/app/services/session/service.py` | `prepare_upload`, `commit_upload`, delete/expire, generation, quotas, test hooks |
| `backend/app/services/documents/service.py` | Off-lock stream/validate; provisional cleanup `finally`; delete delegates to session |
| `backend/app/services/documents/validation.py` | `assert_safe_zip_member_name`, `inspect_docx_zip`, macro detection |
| `backend/app/models/taxonomies.py` / `domain_errors.py` | `upload_macros_not_supported` |
| `backend/tests/unit/test_upload_races.py` | Barrier/event race suite |
| `backend/tests/unit/test_docx_security.py` | Path + macro matrix |
| `backend/tests/integration/test_sessions.py` | Macro/unsafe ZIP API + residue |
| `frontend/src/app/App.tsx` / `api/client.ts` / schemas | UI status + Zod wire validation |
| Readiness + contracts docs | OD-05, matrix, error-codes |

## 1. Git and scope verification — PASS

- Audited tree is exactly `5ab566ff7ad63e51ee8a08f2c7b5ebb6bccec093`.
- `phase-01-pass` remains peeled `1d9c612…`.
- Hardening delta is Phase 1 security/concurrency/docs/tests only.
- No confidential case binaries, credentials, OCR weights, `node_modules`, venvs, or runtime session dirs committed (see §8).

## 2. Concurrency hardening audit — PASS

### Lifecycle

1. **`prepare_upload` (locked):** live session + touch; returns `uploads_dir` + `generation`; optional `after_prepare` test hook.
2. **Validate (unlocked):** stream, signature/MIME, inspect, hash, rename provisional → stable internal name.
3. **`commit_upload`:** `before_commit` hook **outside** the lock (avoids deadlock with delete/expire); then locked re-check of registry presence, expiry, generation, file-count, hash duplicate, total bytes/pages; register atomically.
4. **`DocumentService` `finally`:** deletes provisional/stable blob if commit did not succeed (or duplicate’s unused blob).

### Checklist

| Requirement | Result |
|-------------|--------|
| Session existence/activity rechecked at final commit | Yes — registry/status/expiry/generation |
| Document mutations via synchronized `SessionService` | Yes — register + delete under `RLock` |
| Upload cannot commit after explicit delete | Yes — registry pop + generation bump; `session_not_found` |
| Upload cannot commit after expiry | Yes — expire path; `session_expired` or `session_not_found` |
| Document delete via same service boundary | Yes — `DocumentService.delete_document` → `SessionService.delete_document` |
| Provisional removed after failed/lost commit | Yes — DocumentService `finally` (+ delete/expire tree wipe) |
| Cleanup idempotent | Yes — delete session/document; repeated expiry cleanup |
| No orphan record without file / file without record (API path) | Yes — commit requires existing blob; failures clean blob; duplicates share one owner path |
| Lock not held during stream/ZIP/hash | Yes |
| No lock-order inversion | Single `RLock`; `before_commit` outside lock |

### Independent race reproduction

Shipped barrier/event tests (no sleep-only synchronization):

| Scenario | Evidence |
|----------|----------|
| Upload vs explicit deletion | `test_upload_races_explicit_session_delete` |
| Upload vs expiry | `test_upload_races_session_expiry` |
| Two uploads × file-count limit | `test_two_commits_race_file_count_limit` |
| Two uploads × total-size limit | `test_two_commits_race_total_size_limit` |
| Two identical SHA uploads | `test_two_identical_uploads_concurrent` |
| Cleanup after failed final commit | `test_lost_registration_cleans_provisional` |
| Macro/unsafe residue via API | integration tests |

Additional **ad hoc probes** (not committed; executed against the audited tree):

| Probe | Result |
|-------|--------|
| Simultaneous commits on **separate sessions** | Both succeed; lists isolated |
| Document delete while another upload commits | Delete applies; competing commit still succeeds for new blob |
| File-count loser + DocumentService-style `finally` cleanup | One record, one file, `upload_file_count_exceeded` for loser |

Focused pytest subset: **26 passed**.

## 3. Atomic limit enforcement — PASS

Authoritative decisions for file count, total session bytes, and SHA duplicate ownership occur **inside** locked `commit_upload` against current session state. Prechecks cannot jointly exceed limits: one winner, one contracted rejection. Rejected competitors do not reserve `bytes_used` / `pages_used` / `hash_index`. With DocumentService cleanup, rejected competitors leave no document record and no leftover blob.

## 4. DOCX member-path validation — PASS

`assert_safe_zip_member_name` normalizes `\` → `/`, then rejects empty/null-byte names, POSIX absolute (`/…`), UNC (`//…`), drive-qualified (`C:…`), and any `..` path segment. `inspect_docx_zip` uses `ZipFile` metadata/`read` only — **no extract to session disk**.

Independent probes rejected all checklist examples, including:

`/word/document.xml`, `\word\document.xml`, `C:\word\document.xml`, `C:/word/document.xml`, `\\server\share\file`, `../word/document.xml`, `word/../../file`, `word\..\..\file`, `word/../file`, mixed separators.

Valid relative OOXML names (`word/document.xml`, `[Content_Types].xml`) accepted. Unit matrix + integration unsafe-entry upload confirmed.

## 5. Macro-bearing DOCX validation — PASS

Detection paths verified:

| Path | Result |
|------|--------|
| `word/vbaProject.bin` (case variants e.g. `Word/VbaProject.bin`) | Rejected |
| `word/vbaData.xml` | Rejected (probe) |
| VBA Content_Types overrides | Rejected |
| VBA package/document relationships | Rejected |
| Renamed `.docm` as `.docx` fixture | Rejected |
| Clean macro-free DOCX | Accepted |

Contracted error: `upload_macros_not_supported` in `docs/contracts/error-codes.md`, `ErrorCode` enum, and `ERROR_MESSAGES`. `UploadRejection.error_code` remains a string in JSON Schema/Zod (pre-existing pattern for all upload codes); runtime emits the catalogue code. Integration asserts empty `uploads/` and empty document list; messages omit internal ZIP member paths / `vba` leakage.

## 6. OD-05 and document status — PASS

Consistent across:

- `docs/readiness/open-decisions.md` OD-05 status
- `docs/readiness/phase-acceptance-matrix.md` Phase 1 Nonblocking
- `docs/implementation-reports/phase-01-completion.md`
- UI: `status === "uploaded"` → “Awaiting normalization” (DOCX notes viewing PDF/thumbnails in a later phase)
- Contracts: `DocumentStatus.uploaded` = accepted into session storage; normalization is a later status

Phase 1 securely stores valid DOCX as `uploaded`. DOCX→PDF and thumbnails remain Phase 2. Future conversion failure is a Phase 2 processing error/issue — not a Phase 1 upload invalidation. Frontend validates upload batch/document responses via Zod (`DocumentUploadBatchSchema` / `DocumentSchema`).

## 7. Regression verification

**Environment:** clean worktree at `5ab566f`; Python `D:\Applications\VeriDemand\.tools\python312\python.exe` (3.12.8); `uv sync --frozen --extra dev --python …`; frontend `npm ci` from committed lockfile.

| Command | Result |
|---------|--------|
| `uv sync --frozen --extra dev` | PASS (no lockfile mutation) |
| `ruff format --check app tests` | PASS (69 files) |
| `ruff check app tests` | PASS |
| `mypy app` | PASS (56 files) |
| `pytest -q` | **83 passed** |
| `npm ci` | PASS |
| `npm run format:check` / `lint` / `typecheck` | PASS |
| `npm test` (vitest) | **6 passed** |
| `npm run build` | PASS |
| Contract generate + `check-contracts.mjs` | **OK — no drift** (25 schemas) |
| `proof-drift-fails.mjs` | **OK** |
| Delete generated artifacts → regen ×2 → SHA-256 compare | **DETERMINISM_OK** (52 files identical across rounds) |
| `node scripts/check-all.mjs` | **All Phase 1 checks passed** (exit 0) |

**Regressions:** none observed.

## 8. Repository safety — PASS

On committed tree `5ab566f`:

- No `.env` (only `.env.example`), credentials, venvs, `node_modules`, `__pycache__`, OCR model weights
- No `docs/example/**/*.pdf` / case DOCX binaries tracked
- No runtime `tmp/sessions` contents tracked
- Absolute local paths appear only in prior **implementation/audit reports** as verification-worktree notes (not production code or secrets)

## Blocking defects

**None.**

## Nonblocking observations

1. Cross-session concurrent commits and document-delete-during-upload are covered by ad hoc probes here; consider promoting them into `test_upload_races.py` for permanent CI.
2. SessionService-level quota race tests leave the loser’s blob until DocumentService `finally` (by design of the split). Production API path is clean.
3. Macro XML reads use canonical OOXML paths (`[Content_Types].xml`, etc.); entry-name macro checks are case-insensitive. Exotic ZIP case folding for those XML paths remains a theoretical edge case.
4. Periodic sweeper **interval** still not asserted beyond lifespan shutdown + callable cleanup (unchanged from prior audit).
5. Generated Zod still loose on some enums (`z.any()` / string error codes); FE overlays tighten wire paths.
6. Module docs 01/02 still `Status | design` while Phase 1 is implemented (docs hygiene).
7. Frontend `npm audit` reports transitive high/critical advisories in the lockfile tree — triage separately from Phase 1 functional gate.

## Final verdict

# PASS

Hardening commit `5ab566ff7ad63e51ee8a08f2c7b5ebb6bccec093` correctly and completely closes the material Phase 1 audit findings (S-01/S-02/S-03, D-01/D-02) without regressions or Phase 2 scope creep. Independent gates reproduce **83** backend and **6** frontend tests green; contract drift checks and double regeneration are deterministic.

**Commit `5ab566ff7ad63e51ee8a08f2c7b5ebb6bccec093` is suitable for the immutable tag `phase-01-audited-pass`.**

This audit did **not** create that tag. Phase 2 was **not** started.

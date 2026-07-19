# Phase 1 Independent Audit — Temporary Session and Secure Upload

**Audit date:** 2026-07-19  
**Auditor:** Independent verification against tagged Phase 1 (not the completion report’s PASS)  
**Method:** Clean detached worktree + lockfile-only dependency sync + code inspection + adversarial probes + full quality gate reproduction  

## Audited tag and commit

| Item | Value |
|------|-------|
| Tag | `phase-01-pass` (annotated) |
| Tag object | `eed0412b185c1ef45982a549e05ad5c17b38f23d` |
| **Peeled commit** | `1d9c6127a555995d312daf8e051205bfc664a5dd` |
| Commit subject | `phase-01: record completion commit hash in phase report` |
| Phase 0 baseline tag | `phase-00-pass` → peeled `aad013cb56b3c366583761f8eab51b03876e4a24` |
| Phase 0 unchanged | Confirmed — `phase-00-pass^{}` still `aad013c…`; ancestor of Phase 1 |
| Verification worktree | `D:\Applications\VeriDemand-phase01-audit` at detached `1d9c612` (clean before/after gate) |

**Note:** `git rev-parse phase-01-pass` returns the annotated tag object; peel with `phase-01-pass^{}` / `^{commit}` for the audited tree.

## Diff reviewed

```text
git diff --stat phase-00-pass..phase-01-pass
# 43 files changed, 3077 insertions(+), 30 deletions(-)
```

Commits in range: 2 (`85160a3` implement; `1d9c612` completion hash).

**Areas touched:** backend session/documents services + API + lifespan sweeper; upload validation/inspect; tests/fixtures; `DocumentUploadBatch` / `UploadRejection` contracts + generated JSON Schema/Zod; frontend session/upload UI + client; OD-04/OD-05 status; phase-01 completion report; deps (`pypdf`, `Pillow`, `python-multipart`).

**Scope-drift scan:** No OCR, pdfplumber, PDF.js viewer, classification, billing, LLM, drafting, export, LibreOffice conversion, or thumbnail-generation routes/deps in the Phase 1 diff.

**Repository hygiene (tagged tree):** No credentials/`.env` (non-example), no case PDF/DOCX binaries under `docs/example/`, no OCR weights, no `tmp/sessions` contents. Only committed binary of note: `docs/prototype_documentation.docx` (product doc, not case evidence).

## Requirements checked

| ID | Result | Evidence summary |
|----|--------|------------------|
| FR-SES-01 | Met | Opaque `ses_` + `secrets.token_urlsafe(18)`; `expires_at` from TTL |
| FR-SES-02 | Met | In-memory registry; workspace under `temp_root/<session_id>/` |
| FR-SES-03 | Met | DELETE idempotent; UI reset = DELETE+POST; trees removed |
| FR-SES-04 | Met | Lifespan asyncio sweeper + `cleanup_expired_sessions` + lazy expire on get |
| FR-SES-05 | Met | `CaseSession.warning` + UI banner |
| FR-UPL-01 | Met | PDF, DOCX, JPG, PNG, TIFF accepted (integration matrix) |
| FR-UPL-02 | Met | Extension + MIME + signature; mismatches rejected |
| FR-UPL-03 | Met | Random internal names; basename-only display names |
| FR-UPL-04 | Met | SHA-256 exact duplicate → `status: duplicate` |
| FR-UPL-05 | Met | Encrypted/corrupt/unsupported/oversized → `upload_*` codes |
| FR-UPL-06 | Soft deferred | OD-05 option C; no DOCX→PDF |
| FR-UPL-07 | Deferred to Phase 2 | Thumbnails not generated; PDF/image/TIFF page counts present; DOCX `page_count` null |
| Exit gate | Met with gaps | Upload + cleanup verified on synthetics; no OCR/AI; Amini package binaries absent |
| OD-04 | Resolved | Lifespan sweeper + test-callable cleanup |
| OD-05 | Soft-deferred (authorized) | Accept DOCX after ZIP/OOXML inspect; wording tension with matrix “explicit error” |

Module exit gates (01 residual files; 02 sample package + safe reject) are satisfied for synthetic fixtures; Module 02 “supplied sample package” / matrix Amini row is **not** literally exercised (see deferred / gaps).

## Tests independently run

### Environment

- Worktree: clean detached `1d9c612`
- Python: `D:\Applications\VeriDemand\.tools\python312\python.exe` (3.12.8)
- Backend: `uv sync --frozen --extra dev` (committed `backend/uv.lock`)
- Frontend: `npm ci` (committed `frontend/package-lock.json`)

### Commands and results

| Command | Result |
|---------|--------|
| `ruff format --check app tests` | PASS |
| `ruff check app tests` | PASS |
| `mypy app` | PASS (56 files) |
| `pytest -q` | **54 passed** |
| `scripts/generate_json_schemas.py` | PASS (25 schemas) |
| `node scripts/generate-zod.mjs` | PASS (25 modules) |
| `node scripts/check-contracts.mjs` | **contracts:check OK — no drift** |
| `node scripts/proof-drift-fails.mjs` | **drift-check proof OK** |
| `npm run format:check` | PASS |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `npm test` (vitest) | **6 passed** |
| `npm run build` | PASS |
| `node scripts/check-all.mjs` | **All Phase 1 checks passed** (exit 0) |

Windows note: regenerating JSON Schema on this host rewrites files with CRLF; `check-contracts` content-compares as no drift. Working tree restored to clean tagged state after verification.

### Focused / adversarial probes (temporary; not committed)

15 additional probes executed then deleted from the worktree:

| Probe | Result |
|-------|--------|
| Lifespan enter/exit cleans remaining session dirs | PASS |
| Upload after forced expiry → `410 session_expired` | PASS |
| Cross-session document delete is no-op for foreign doc; owner retains | PASS |
| Random / path-like session IDs → `session_not_found`; no path disclosure | PASS |
| Metadata after session delete → 404; no `uploads`/temp paths in body | PASS |
| PNG bytes as `.pdf` → `upload_signature_mismatch` | PASS |
| `.docm` rejected `upload_unsupported_type` | PASS |
| Plain ZIP without OOXML rejected | PASS |
| `../` ZIP entry rejected | PASS |
| Absolute ZIP entry `/tmp/evil.txt` **accepted** (not extracted) | Behavior recorded (gap) |
| `application/octet-stream` + valid DOCX accepted | PASS |
| `application/zip` MIME + valid DOCX accepted | PASS |
| DOCX with `word/vbaProject.bin` accepted | Behavior recorded (gap) |
| Upload then session delete leaves no residue | PASS |
| Oversized / partial cleanup (existing suite) | PASS |

**Coverage gaps remaining in shipped tests:** no true concurrent upload-vs-delete race; no assertion that the periodic sweeper tick fires (callable cleanup + lifespan shutdown cleanup are covered).

## Security findings

### Strengths

- Opaque session IDs via `secrets.token_urlsafe`; workspace creation rejects traversal in `session_id`.
- Streaming size limit during write (`_stream_to_disk`); rejected/incomplete blobs deleted in `finally`.
- Extension/MIME/signature agreement; DOCX ZIP entry count, uncompressed total, compression ratio, nested `.zip`, and `../` checks.
- Validation inspects ZIP metadata via `ZipFile` without extracting into the session tree.
- API responses omit filesystem paths; logs omit document body bytes (integration assertion).
- Cross-session list isolation; foreign document delete does not remove another session’s document.
- Shutdown lifespan cancels sweeper (`cancel` + await `CancelledError`) and deletes remaining sessions.

### Issues

| ID | Severity | Requirement | Finding |
|----|----------|-------------|---------|
| S-01 | Medium (nonblocking for Phase 1 prototype) | Isolation / concurrency | `DocumentService._ingest_one` mutates `SessionRecord` outside `SessionService` lock for most of the upload. Concurrent upload/delete can race. No shipped stress test. |
| S-02 | Low | DOCX container audit | Absolute entry names (e.g. `/tmp/evil.txt`) are **not** rejected. No extract occurs today, so no escape observed. |
| S-03 | Low | FR-UPL / macros | A `.docx` containing `word/vbaProject.bin` is accepted after OOXML checks. `.docm` is correctly rejected by extension. |
| S-04 | Info | Auth model | Capability = knowledge of opaque `session_id` only (expected for temporary prototype; not multi-tenant auth). |
| S-05 | Info | MIME looseness | DOCX allows `application/zip` and any type allows `application/octet-stream` when signature/extension agree — acceptable with signature gate; polyglot residual risk remains. |

### Defect write-up (S-01)

- **Severity:** Medium (nonblocking for Phase 1 exit; relevant before multi-user load)
- **Affected:** FR-SES-02/03 isolation under concurrency; audit requirement for concurrent upload/deletion
- **Reproduction:** Inspect `DocumentService._ingest_one` vs `SessionService` lock scope; note absence of concurrent tests
- **Expected:** Registry mutations under lock for full ingest, or documented single-flight guarantee + tests
- **Actual:** Brief lock only around session lookup; long stream/inspect unlocked
- **Recommended correction:** Hold lock around metadata commits; or per-session asyncio lock for ingest/delete; add concurrent TestClient/httpx stress tests

### Defect write-up (S-02)

- **Severity:** Low
- **Affected:** DOCX container path rules
- **Reproduction:** ZIP with `[Content_Types].xml`, `word/`, and entry `/tmp/evil.txt` → `inspect_docx_zip` succeeds; no file written under temp root
- **Expected:** Reject absolute/UNC entry names per audit checklist
- **Actual:** Accepted; not extracted
- **Recommended correction:** Reject names starting with `/`, drive letters, or backslash-absolute forms

## Contract findings

- Additive Phase 1 entities `DocumentUploadBatch` / `UploadRejection` present in docs, Pydantic registry, JSON Schema, and Zod.
- `contracts_version` remains **0.1** (additive) — consistent with completion claim.
- Emitted session/upload error codes match `docs/contracts/error-codes.md` / `ErrorCode` enum; handlers use catalogue messages.
- Frontend `client.ts` validates session/document/batch/error envelopes with Zod (`safeParse`) rather than blind trust.
- Drift detection works (`proof-drift-fails.mjs` OK).
- Known soft gap (also in completion report): generated Zod still uses `z.any()` for some enums; FE overlays tighten wire paths.

## Deferred-requirement findings

| Check | Result |
|-------|--------|
| OD-05 authorizes deferral | **Yes** — status 2026-07-19 soft-deferred option **C** |
| Matrix marks nonblocking | **Yes** — Phase 1 Nonblocking: OD-05 |
| Later phase owns FR-UPL-06/07 | **Yes** — Phase 2 FR IDs include FR-UPL-06..07 |
| Deferral does not block Phase 1 exit gate | **Yes** — exit gate is reference upload + cleanup; no OCR/AI |
| Completion report records deferral | **Yes** |

**Wording tension (nonblocking gap D-01):** Matrix Nonblocking line and OD-05 *Recommended* say missing converter → **explicit error**. Phase 1 **Status** chose option **C** (accept DOCX, no conversion, no converter-missing error). Status + soft FR-UPL-06 language authorize Phase 1 exit without LibreOffice; the “explicit error” phrase is **not** implemented. Treat as documentation/consistency gap, not an invalid deferral under the written OD-05 status.

**FR-UPL-07:** Correctly owned by Phase 2 in the matrix; deferral of thumbnails is valid. Partial page counts for PDF/images/TIFF are extra progress.

## Scope-drift findings

- No Phase 2 functionality introduced (no viewer, native extraction, OCR, classification, chronology, billing, issues, LLM, drafting, export).
- Dependencies added are upload-scoped (`pypdf`, `Pillow`, `python-multipart`) and inventoried.
- Phase 0 tag not moved.

## Reproduction results (exit-gate lens)

| Criterion | Independent result |
|-----------|-------------------|
| Upload valid/invalid types | PASS (automated) |
| SHA duplicate | PASS |
| Session delete cleans files | PASS |
| TTL cleanup callable | PASS |
| Lifespan shutdown cleanup | PASS (adversarial) |
| No OCR/AI | PASS (diff + deps) |
| Reference / Amini package upload | **Not executed** — package binaries not in repo (`docs/example/` gold markdown only); evidence is synthetic fixtures |
| Refresh/session warning UI | Present in `App.tsx` (code review; not browser E2E in this audit) |

## Blocking defects

**None** that invalidate FR-SES-01..05, FR-UPL-01..05, OD-04 resolution, or the core exit gate (upload + cleanup + no OCR/AI) under independent reproduction.

## Nonblocking improvements

1. **D-02 — Reference fixture evidence:** Record that Amini binaries are intentionally absent; either add a sanitized miniature “reference” fixture set under tests, or update the acceptance matrix “Reference fixture” row to match synthetic-only Phase 1 evidence.
2. **D-01 — OD-05 wording:** Align matrix Nonblocking text with option C (or emit an explicit `upload_*` / `not_implemented` when conversion is skipped).
3. **S-01 — Concurrency:** Per-session lock + race tests.
4. **S-02 / S-03 — DOCX hardening:** Reject absolute ZIP paths; optionally flag/reject `vbaProject.bin`.
5. **Sweeper test:** Assert periodic sweeper task creation/cancellation under lifespan (beyond shutdown cleanup).
6. **FE:** Wire `PendingUpload` / `setPending` or remove dead store surface.
7. **Docs hygiene:** Modules 01/02 still `Status | design` while Phase 1 is tagged PASS — update status markers.
8. Frontend `npm audit` reported high/critical advisories in the lockfile tree (transitive); triage separately from Phase 1 functional gate.

## Final verdict

# PASS WITH GAPS

Phase 1 at `phase-01-pass` / `1d9c612` **does** satisfy FR-SES-01..05 and FR-UPL-01..05 with independently reproduced automated evidence, OD-04 is resolved, FR-UPL-06/07 deferral is authorized by OD-05 status and the Phase 2 FR split, and no Phase 2/OCR/AI scope creep was found.

It is **not** a clean **PASS** because of material nonblocking gaps: matrix Amini/reference-package evidence was not reproduced (synthetic-only), OD-05 “explicit error” vs option C inconsistency, missing concurrency/sweeper-tick test coverage, and minor DOCX container hardenings (absolute ZIP entries; macro-bearing OOXML accepted).

Do **not** start Phase 2 until product owners accept these gaps or close D-02 / D-01 as documentation updates.

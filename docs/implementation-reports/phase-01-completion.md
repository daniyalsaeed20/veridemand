# Phase 1 Completion Report — Temporary Session and Secure Upload

**Date:** 2026-07-19  
**Modules:** [01-session-and-workspace.md](../modules/01-session-and-workspace.md), [02-upload-validation-normalization.md](../modules/02-upload-validation-normalization.md)  
**Acceptance matrix:** [phase-acceptance-matrix.md](../readiness/phase-acceptance-matrix.md) Phase 1  

## Closure identifiers

| Item | Value |
|------|-------|
| Phase 0 baseline commit | `aad013cb56b3c366583761f8eab51b03876e4a24` (`phase-00-pass`) |
| Phase 1 branch | `phase-01-session-upload` |
| Phase 1 commit | Prefer `git rev-parse phase-01-pass^{commit}` (tag tip after tagging) |
| Tag | `phase-01-pass` (created only on PASS) |

## Scope implemented

- In-memory `SessionService` with opaque IDs, TTL, workspace under `TEMP_ROOT` / default `tmp/sessions`
- Asyncio lifespan TTL sweeper + callable `cleanup_expired_sessions` (OD-04 resolved)
- Secure multipart upload: extension + MIME + signature, SHA-256, duplicates, size/count/page limits
- DOCX ZIP/OOXML inspection with decompression limits (no LibreOffice conversion)
- Safe page counts for PDF/images/TIFF; DOCX `page_count` null in Phase 1
- API: create/get/delete session; upload/list/delete documents; contracted error envelopes
- React upload UI: temporary banner, session warning, drag/drop, accepted/rejected/duplicate, reset, expiry
- Synthetic fixtures and automated tests; contract regen for `DocumentUploadBatch` / `UploadRejection`

**Not implemented (by design):** OCR, native text extraction, classification, chronology, billing, issues, LLM, drafting, export, PDF viewer, DOCX→PDF (FR-UPL-06 soft), thumbnails (FR-UPL-07).

## Requirement IDs implemented

| ID | Evidence |
|----|----------|
| FR-SES-01 | Opaque `ses_` IDs + `expires_at` from TTL |
| FR-SES-02 | Process memory registry + session temp directories |
| FR-SES-03 | DELETE / Reset (DELETE+POST); idempotent cleanup |
| FR-SES-04 | Asyncio sweeper + `cleanup_expired_sessions` + expiry on get |
| FR-SES-05 | `CaseSession.warning` + UI Temporary Prototype / session warning |
| FR-UPL-01 | PDF, DOCX, JPG, PNG, TIFF accepted |
| FR-UPL-02 | Extension + MIME + signature agreement |
| FR-UPL-03 | Random internal filenames; `display_name` metadata only |
| FR-UPL-04 | SHA-256 exact duplicate → `status: duplicate` |
| FR-UPL-05 | Encrypted/corrupt/unsupported/oversized → upload_* codes |

## API endpoints

| Method | Path | Notes |
|--------|------|-------|
| `POST` | `/api/v1/sessions` | `CaseSession` |
| `GET` | `/api/v1/sessions/{session_id}` | Touch TTL |
| `DELETE` | `/api/v1/sessions/{session_id}` | `204` idempotent |
| `POST` | `/api/v1/sessions/{session_id}/documents` | Multipart → `DocumentUploadBatch` |
| `GET` | `/api/v1/sessions/{session_id}/documents` | Metadata only |
| `DELETE` | `/api/v1/sessions/{session_id}/documents/{document_id}` | `204` idempotent |

## Contract changes

| Change | Version |
|--------|---------|
| Added `DocumentUploadBatch` / `UploadRejection` entity docs + Pydantic + JSON Schema + Zod | `contracts_version` remains **0.1** (additive) |
| Regenerated `contracts/generated/` and `frontend/src/schemas/generated/` | 25 schemas |

## Security controls

- Temp paths never in API JSON; session IDs cannot traverse out of `temp_root`
- Random internal upload names; basename-only display names
- Signature validation; DOCX decompression limits; no archive uploads except constrained DOCX
- Incomplete uploads deleted; session delete/expiry remove workspace trees
- Logs: IDs/metadata only; no document body text
- `tmp/`, `backend/tmp/`, `data/sessions/` gitignored

## Dependencies added

| Package | Version | Purpose | Licence |
|---------|---------|---------|---------|
| pypdf | 5.9.0 | PDF encrypt/corrupt checks + page count | BSD-3-Clause |
| Pillow | 11.3.0 | Image verify + TIFF frames | HPND |
| python-multipart | 0.0.20 | Multipart upload parsing | Apache-2.0 |

See [DEPENDENCY_INVENTORY.md](../../DEPENDENCY_INVENTORY.md).

## Files created or changed (high level)

- `backend/app/services/session/`, `backend/app/services/documents/`
- `backend/app/api/v1/sessions.py`, `backend/app/main.py`, `backend/app/core/{domain_errors,errors,server_settings}.py`
- `backend/app/models/document_upload_batch.py`, registry updates
- `backend/tests/unit/test_session.py`, `test_upload_validation.py`, `integration/test_sessions.py`, `tests/fixtures/`
- `frontend/src/app/App.tsx`, `api/client.ts`, `store/shellStore.ts`, schemas + tests
- `docs/contracts/entities/document-upload-batch.md`, OD-04/OD-05 status, local-setup, this report
- `DEPENDENCY_INVENTORY.md`, `backend/pyproject.toml`, `backend/uv.lock`

## Automated test results

| Suite | Result |
|-------|--------|
| Backend pytest | **54 passed** |
| Frontend vitest | **6 passed** |
| Contract drift proof | **OK** |
| `node scripts/check-all.mjs` | **All Phase 1 checks passed** |

## Manual acceptance results

Scripted against `TestClient` + synthetic fixtures (2026-07-19):

| Check | Result |
|-------|--------|
| Create session | PASS |
| Upload supported synthetic PDF/DOCX/PNG | PASS |
| Invalid file rejected; session remains | PASS |
| Exact duplicates identified | PASS |
| Session isolation | PASS |
| Delete removes temp directory | PASS |
| Expiry cleanup + inaccessible | PASS |
| Temporary-session warning present | PASS |

## Cleanup evidence

- Unit/integration tests assert workspace removal on delete and expiry
- Repeated `cleanup_expired_sessions` returns empty after first sweep
- Failed oversized uploads leave empty `uploads/` directory
- Shutdown lifespan deletes remaining sessions

## Known gaps

| Gap | Severity |
|-----|----------|
| FR-UPL-06 DOCX→PDF viewing copy (LibreOffice) deferred (OD-05 soft) | Soft / nonblocking |
| FR-UPL-07 thumbnails not generated | Soft / deferred to Phase 2 viewer |
| DOCX `page_count` null until normalize | Expected Phase 1 |
| Generated Zod still loose on some enums (`z.any()`); FE overlays tighten wire paths | Nonblocking |

## Deferred work

Phase 2+: page analysis / native extraction / OCR, classification, facts, chronology, billing, issues, drafting, export, DOCX→PDF + thumbnails.

## Exit-gate evidence

| Gate criterion | Evidence |
|----------------|----------|
| FR-SES-01..05 | Session service + API + UI warning + tests |
| FR-UPL-01..05 | Validation pipeline + integration matrix |
| Reference upload + cleanup | Manual script + automated cleanup tests |
| No OCR/AI | No OCR/LLM deps or routes added |
| OD-04 resolved | Asyncio sweeper + callable cleanup |
| UPL-06 soft | Documented; DOCX accepted after ZIP inspect only |

## Open decisions updated

- **OD-04:** Resolved — asyncio lifespan sweeper + test-callable cleanup
- **OD-05:** Soft-deferred — no LibreOffice in Phase 1; FR-UPL-06 known gap

## Repository safety

| Category | Result |
|----------|--------|
| Secrets / `.env` (excl. examples) | PASS |
| Real case PDF/DOCX | PASS — synthetic fixtures only |
| Temp session dirs | PASS — gitignored |
| Lockfiles | `backend/uv.lock`, `frontend/package-lock.json` updated |

## Final verdict

# PASS

FR-SES-01..05 and FR-UPL-01..05 satisfied with automated and manual evidence. FR-UPL-06/07 remain soft gaps as allowed by the acceptance matrix. Phase 2 was not started. Phase 0 tag `phase-00-pass` was not modified.

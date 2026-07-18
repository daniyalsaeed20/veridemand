# API Error Codes

**error_codes_version:** `0.1`  
**Status:** design (Markdown SoT for machine-readable API errors)

## Purpose

Canonical `error_code` values for FastAPI JSON errors. Complements in-session **Issues** ([issue-types.md](./issue-types.md)), which are review-queue items—not HTTP failures.

Prototype §14.1: return machine-readable codes plus user-facing messages. Never put filesystem paths, secrets, or document body text in `message` / `details` when `LOG_DOCUMENT_TEXT=false`.

## API vs Issue

| Kind | When to use | Where shown |
|------|-------------|-------------|
| **API error** (`error_code`) | Request cannot complete (auth/session, validation, engine crash, hard blocker on export call) | Toast / inline form error / HTTP response |
| **Issue** (`issue_type`) | Case content needs human review (conflict, low OCR, placeholder in draft) | Issues panel / Green-Amber-Red queue |

Example: unreadable page → usually an **Issue** (`extraction.unreadable_page`). OCR **process** crash → API `extraction_ocr_failed`.

## Response envelope

```json
{
  "error_code": "session_expired",
  "message": "This temporary session has expired.",
  "details": {},
  "session_id": "ses_01JEXAMPLE000000000000000",
  "document_id": null,
  "request_id": "req_01JEXAMPLE"
}
```

| Field | Required | Rules |
|-------|----------|-------|
| `error_code` | yes | snake_case from this catalog |
| `message` | yes | User-facing; stable enough for UI |
| `details` | no | Safe machine fields only (e.g. `stage`, `limit`, `max`) |
| `session_id` | no | When scoped |
| `document_id` | no | When scoped |
| `request_id` | no | Correlation / developer support |

Upload per-file failures may also appear as objects in a **200** multi-status upload response using the same `error_code` + `message` fields (module 02).

---

## Session

| error_code | HTTP | message (template) | Recovery | Module |
|------------|------|--------------------|----------|--------|
| `session_not_found` | 404 | Session not found. | Start a new case. | 01 |
| `session_expired` | 410 | This temporary session has expired. | Start a new case. | 01 |
| `session_cleanup_failed` | 500 | The session could not be fully cleaned up. | Retry delete/reset; contact developer if it persists. | 01 |
| `session_limit_exceeded` | 429 | Too many active sessions. | Wait and retry; stop other demos. | 01 |

---

## Upload

Aligns with module 02; codes may be used without `upload_` prefix for parity with existing design names, or with prefix in HTTP envelope—**canonical codes below** (prefer these going forward).

| error_code | Alias (module 02) | HTTP | message (template) | Recovery | Module |
|------------|-------------------|------|--------------------|----------|--------|
| `upload_unsupported_type` | `unsupported_type` | 400 | This file type is not supported in the prototype. | Remove or convert the file. | 02 |
| `upload_mime_mismatch` | `mime_mismatch` | 400 | File content does not match its declared type. | Re-export or re-save the file and retry. | 02 |
| `upload_signature_mismatch` | `signature_mismatch` | 400 | File signature validation failed. | Provide a valid PDF/DOCX/image. | 02 |
| `upload_encrypted_pdf` | `encrypted_pdf` | 400 | This PDF is password-protected and cannot be processed. | Provide an unlocked copy. | 02 |
| `upload_corrupt_file` | `corrupt_file` | 400 | This file appears corrupt or unreadable. | Re-export and retry. | 02 |
| `upload_file_too_large` | `file_too_large` | 400 | This file exceeds the maximum size limit. | Split or compress; check `MAX_FILE_SIZE_MB`. | 02 |
| `upload_page_limit_exceeded` | `page_limit_exceeded` | 400 | This file exceeds the page limit for the session. | Reduce pages or raise `MAX_PAGES_PER_SESSION` for demos. | 02 |
| `upload_total_size_exceeded` | — | 400 | Total upload size for this session was exceeded. | Remove files; check `MAX_TOTAL_UPLOAD_MB`. | 02 |
| `upload_file_count_exceeded` | — | 400 | Too many files in this session. | Remove files; check `MAX_FILES_PER_SESSION`. | 02 |
| `upload_duplicate` | (status `duplicate`) | 200* | This file is an exact duplicate of another upload. | Keep one copy; exclude the duplicate. | 02 |

\*Duplicate may be returned as a document with `status: duplicate` rather than a hard error.

---

## Process / job

| error_code | HTTP | message (template) | Recovery | Module |
|------------|------|--------------------|----------|--------|
| `process_not_ready` | 409 | Documents are not ready to process. | Finish uploads; fix rejected files. | pipeline |
| `process_already_running` | 409 | A processing job is already running for this session. | Wait for progress events. | pipeline |
| `process_cancelled` | 409 | Processing was cancelled. | Start process again if needed. | pipeline |
| `process_stage_failed` | 500 | Processing failed during stage `{stage}`. | Retry once; check `details.stage` / `request_id`. | pipeline |

`details.stage` should use job stages from prototype §14.3 (e.g. `ocr`, `extracting_deterministic`).

---

## Extraction

Prefer **Issues** for per-page quality. Use API errors when the engine cannot run.

| error_code | HTTP | message (template) | Recovery | Module |
|------------|------|--------------------|----------|--------|
| `extraction_render_failed` | 500 | A page could not be rendered for OCR. | Retry; exclude document if persistent. | 03 |
| `extraction_ocr_failed` | 500 | OCR failed on one or more pages. | Retry; open page quality warnings; enter values manually. | 03 |
| `extraction_native_failed` | 500 | Native text extraction failed unexpectedly. | Retry; fall back to OCR path if available. | 03 |

User-facing copy for soft failures (readable UI, not always HTTP): *Text could not be read reliably on specific pages.* → open Issues / page flags (`extraction.*` issue types).

---

## Facts / review

| error_code | HTTP | message (template) | Recovery | Module |
|------------|------|--------------------|----------|--------|
| `fact_not_found` | 404 | Fact not found. | Refresh facts list. | 05/08 |
| `fact_locked` | 409 | This fact is locked and cannot be changed automatically. | Attorney unlock/edit flow if allowed. | 08 |
| `fact_invalid_patch` | 400 | The fact update is invalid. | Fix value/reason; see `details`. | 05/08 |
| `issue_not_found` | 404 | Issue not found. | Refresh issues queue. | 07/08 |
| `issue_invalid_resolution` | 400 | That resolution is not valid for this issue. | Choose a listed option. | 08 |

---

## Draft / export

| error_code | HTTP | message (template) | Recovery | Module |
|------------|------|--------------------|----------|--------|
| `draft_not_ready` | 409 | The case is not ready to generate a demand. | Resolve Red blockers; approve required facts. | 09 |
| `draft_not_found` | 404 | Draft not found. | Generate a draft first. | 09 |
| `draft_llm_schema_failed` | 502 | AI analysis returned an invalid result. | Retry once; preserve prior evidence; use `request_id`. | 09/11 |
| `export_blocked_red_issues` | 409 | The demand cannot be finalized because required issues remain. | Open blocking issues. | 10 |
| `export_blocked_preflight` | 409 | Preflight checks failed. | Open preflight report; fix placeholders, math, unsupported statements. | 10 |
| `export_failed` | 500 | Export failed. | Retry; check template; use `request_id`. | 10 |

---

## Generic

| error_code | HTTP | message (template) | Recovery | Module |
|------------|------|--------------------|----------|--------|
| `route_not_found` | 404 | The requested API route was not found. | Check the path and API version (`/api/v1/...`). | all |
| `validation_error` | 422 | Request validation failed. | Fix fields listed in `details`. | all |
| `internal_error` | 500 | An unexpected error occurred. | Retry; provide `request_id` to a developer. | all |
| `not_implemented` | 501 | This capability is not enabled in the prototype. | Use supported path (e.g. LLM extraction off). | flags |

`route_not_found` is for **unknown HTTP routes only** (no matching FastAPI path). Do **not** use it for missing domain resources — use `session_not_found`, `fact_not_found`, `issue_not_found`, `draft_not_found`, etc.

---

## §13.8 coverage map

| UI condition | Primary code / issue |
|--------------|----------------------|
| Unsupported file | `upload_unsupported_type` |
| Encrypted PDF | `upload_encrypted_pdf` |
| Extraction failure (pages) | Issues `extraction.*` and/or `extraction_ocr_failed` |
| LLM schema failure | `draft_llm_schema_failed` |
| Session expiry | `session_expired` |
| Export blocker | `export_blocked_red_issues` / `export_blocked_preflight` |

---

## Changelog

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-07-18 | Initial error catalog (Pass 5) |
| 0.1 | 2026-07-19 | Add `route_not_found` for unknown API routes (Phase 0 closure) |

# Phase 4 security review

Security and privacy posture for Phase 4 visual detection and printed OCR
(Corrections 1–7). This document describes engineering controls in the
codebase. It does **not** claim regulatory compliance (HIPAA, GDPR, SOC 2, or
any other regime).

Private regression corpora under `fixtures/private/` are **gitignored** and
must never be committed. Operator reports use opaque labels only.

## Upload validation

Streamed validation (ADR 0005) before extraction:

- Filename normalisation (NFC, strip path separators/controls, length bounds)
- Extension allow-list
- Chunked write with byte budgets and SHA-256
- Magic-byte signature detection
- MIME advisory checks (client vs detected)
- Format-specific structural validation without extraction
- Atomic commit to opaque internal document IDs

Rejects carry stable `ErrorCode` values (size, encryption, corruption,
signature mismatch, macros, archive safety, session limits).

## MIME / signature

Client `Content-Type` is never authoritative. Signature mismatch rejects the
upload. Empty files are rejected during stream.

## Macros

- DOC: `oletools` VBA detection only (no p-code disassembly)
- DOCX: treated as untrusted ZIP; macro-enabled packages rejected
- LibreOffice conversion re-runs Word safety checks before headless convert

## LibreOffice isolation

Headless conversion uses `shell=False`, bounded timeout, isolated per-job
user profile under `staging/libreoffice/<job_id>/`, and controlled temp
environment variables (ADR 0009). Documents must not trigger arbitrary
external resource fetches.

## Temporary files and cleanup

Runtime data lives under the configured temp root (default `./temp`):
originals, canonical PDFs, staging uploads, LibreOffice profiles, OCR
renders (when explicitly enabled), targeted-repair crops, and result JSON.
Cleanup on success, failure, cancellation, session delete/reset, TTL sweep,
and shutdown. Residual trees are guarded by
`scripts/check_no_residual_sessions.py`.

## Subprocess and worker protocol

- Native extraction: dedicated Python worker subprocess (no shell); parent
  supervises poll/timeout/cancel → terminate → kill (ADR 0016)
- OCR: long-lived Paddle worker managed by the API process; request/response
  protocol carries privacy-safe diagnostics, not document transcripts in logs
- LibreOffice: `subprocess` with `shell=False` only

Untrusted PDF parsing and OCR inference never run on the FastAPI event loop.

## PDF range delivery

Canonical PDFs are served with HTTP byte ranges for PDF.js. CORS exposes
`Accept-Ranges`, `Content-Range`, `Content-Length`, and `Content-Type` to the
configured frontend origin so cross-origin range reads work without blank
pages (ADR 0012). Paths remain session-scoped; responses must not expose
local filesystem paths.

## CORS

`CORSMiddleware` allowlists `FRONTEND_ORIGIN` (default
`http://localhost:5173`), credentials enabled, methods limited to standard
REST verbs. Not a substitute for authentication in deployed environments.

## Diagnostic endpoints

Native page APIs default to
`include_verification_candidates=false`. Verification candidates
(`verification_words`, recognition_status=rejected) are diagnostic retention
for embedded OCR routing (ADR 0031 / SoT §10.5) and must not be treated as
accepted extraction. Characters default off unless explicitly requested for
inspection.

## Test injection flags

Settings such as `OCR_INJECT_VISUAL_FAILURE`,
`QUEUE_ADMISSION_TEST_DELAY_SECONDS`, and
`NATIVE_EXTRACTION_TEST_DELAY_SECONDS` exist for controlled acceptance/E2E
only. They must remain disabled (false / 0) in production-like runs.

## Logging

Default logs may include request/session/document IDs, stage, duration, page
count, model name, warning/error codes, and aggregate metrics.

Default logs must **not** include full extracted text, page images,
handwritten or repair crop contents, names/identifiers from documents, or
OCR hypothesis strings.

## SSE

Progress uses Server-Sent Events with validated `ProgressEvent` contracts,
sequence/replay bounds, and per-session connection limits (ADR 0007, 0031).
SSE payloads carry progress and lifecycle metadata — not document text.

## Public models and crops

OCR models are local, bootstrapped assets under `.models/` (gitignored).
Processing does not download models. Targeted-repair crops are runtime-only
under `staging/targeted_repair/` and are deleted after use. Saving rendered
pages requires explicit settings and must not be enabled casually in
production (`OCR_SAVE_RENDERED_PAGES`,
`OCR_ALLOW_SAVE_RENDERED_IN_PRODUCTION`).

## Session deletion and TTL

- Unpredictable session and document IDs
- `SESSION_TTL_SECONDS` default 7200; periodic cleanup worker
- Explicit session deletion removes associated files and in-memory state
- Runtime data is not restored after browser refresh

## Dependency scanning

See [security-review.md](../dependencies/security-review.md) for lockfile
checks and vulnerability triage practice.

## Explicit non-claims

- No regulatory compliance certification or attestation is made here.
- No claim that private medical or legal documents are suitable for cloud
  processing; Phase 4 printed OCR is local.
- Phase 5 vision-LLM controls (API key handling, crop minimisation) are out
  of scope until that phase begins.

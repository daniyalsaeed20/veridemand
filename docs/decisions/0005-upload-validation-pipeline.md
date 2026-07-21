# ADR 0005 - Defensive upload validation pipeline

- Status: Accepted
- Date: 2026-07-22
- Phase: 1

## Context

Users upload multiple documents of mixed formats. The platform must accept only
files it can later process, reject untrustworthy input early and cheaply, and
never trust the client-declared content type. Crucially, Phase 1 must validate
**without** performing any extraction, rendering, or text reading.

## Decision

A single streamed pipeline (`uploads/service.py`) processes each multipart part in
order and makes session-limit decisions as files are admitted:

1. **Filename normalisation** (`filename.py`): NFC, strip path separators,
   control characters and NUL, enforce length, lower-case the extension, and
   derive a safe display name. The original name is never used as a path.
2. **Extension allow-list** (`validators.py`): reject unsupported types before
   reading bytes.
3. **Streamed write** (`storage/file_store.py`): chunked copy to
   `staging/<doc_id>.upload`, counting bytes and computing SHA-256, enforcing the
   single-file and per-session byte budgets *during* the stream (no full-file
   buffering). Empty files are rejected.
4. **Signature detection** (`signatures.py`): magic-byte checks per format.
5. **MIME advisory policy**: flag client/detected inconsistencies.
6. **Format-specific structural validation** — using libraries strictly for
   *validation*, never extraction:
   - **PDF** via `pypdf`: open, detect encryption, count pages.
   - **Image** via `Pillow`: verify integrity, dimensions, frame count, and a
     decompression-bomb pixel bound.
   - **DOCX** (`word_validation.py`): treated as an **untrusted ZIP** — guard
     against zip-bombs, path traversal, entry counts/sizes/ratios, and inspect XML
     with `defusedxml`; reject macro-enabled content.
   - **DOC** via `oletools`: detect VBA macros only (never disassemble p-code).
   - **TXT**: encoding sniff (UTF-8/UTF-16).
7. **Atomic commit**: `os.replace` the staged file to
   `originals/<doc_id>.<ext>`, register the document as `uploaded`, and publish
   `document.uploaded`. Failures clean staging with bounded-retry deletion
   (tolerating transient Windows file locks).

Every rejection carries a **stable `ErrorCode`** (e.g. `upload_too_large`,
`upload_encrypted_pdf`, `upload_corrupt_file`, `upload_signature_mismatch`,
`upload_macros_not_supported`, `upload_archive_unsafe`, `session_limit_exceeded`),
so a partial batch reports precise per-file outcomes.

## Consequences

- Malformed, oversized, encrypted, macro-bearing, or type-spoofed files are
  rejected deterministically and cheaply, before any expensive processing exists.
- `pypdf`/`Pillow`/`oletools`/`defusedxml` are validation-only dependencies; their
  presence does not imply any rendering or extraction capability (see
  `docs/dependencies/`).
- New formats require an explicit allow-list entry plus a dedicated validator, so
  scope cannot expand silently.

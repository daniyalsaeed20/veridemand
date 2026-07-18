# Entity: DocumentUploadBatch

| Field | Value |
|-------|-------|
| Spec | §8.2 / Phase 1 |
| Owning module(s) | [02 Upload](../../modules/02-upload-validation-normalization.md) |
| contracts_version | 0.1 |

## 1. Purpose

Multi-status response for multipart document upload: accepted `Document` records plus per-file rejection objects. HTTP status is **200** when the request reaches the session; individual files may fail without ending the session.

## 2. Fields

### DocumentUploadBatch

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `accepted` | Document[] | yes | | Successfully stored or duplicate metadata records |
| `rejected` | UploadRejection[] | yes | | Per-file failures with contracted `error_code` |

### UploadRejection

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `display_name` | string | yes | non-empty | Original filename (UI only); may be sanitized |
| `error_code` | string | yes | upload_* catalog | From [error-codes.md](../error-codes.md) |
| `message` | string | yes | | User-facing message |

## 3. Validation rules

- Never include filesystem paths or file body text.
- Duplicate exact hashes appear in `accepted` with `Document.status: duplicate` (not in `rejected`).
- Session-level failures (`session_not_found`, `session_expired`) use the standard error envelope, not this batch shape.

## 4. Example JSON

```json
{
  "accepted": [
    {
      "id": "doc_01JEXAMPLE000000000000001",
      "session_id": "ses_01JEXAMPLE000000000000000",
      "display_name": "police-report.pdf",
      "file_type": "pdf",
      "content_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "page_count": 1,
      "classification": null,
      "status": "uploaded",
      "exclude_from_drafting": false,
      "treat_as_secondary_evidence": false
    }
  ],
  "rejected": [
    {
      "display_name": "notes.exe",
      "error_code": "upload_unsupported_type",
      "message": "This file type is not supported in the prototype."
    }
  ]
}
```

## 5. Open / additive notes

Added in Phase 1 for the `POST .../documents` multi-status response.

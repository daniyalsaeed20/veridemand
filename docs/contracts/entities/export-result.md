# Entity: ExportResult

| Field | Value |
|-------|-------|
| Spec | §8.11 / Phase 9 |
| Owning module(s) | [10 Verification, Preflight, and Export](../../modules/10-verification-preflight-and-export.md) |
| contracts_version | 0.1 |

## 1. Purpose

Outcome of a DOCX (and optional PDF preview) export after preflight. Final export must not succeed when the programmatic gate is blocked.

## 2. Fields — ExportArtifact

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `artifact_id` | string | yes | prefix `art_` | Opaque download id |
| `content_type` | string | yes | MIME | DOCX or PDF |
| `status` | string | yes | `available` \| `failed` \| `skipped` | PDF may fail while DOCX succeeds |
| `filename` | string | no | basename only | Never a filesystem path |
| `warning` | string \| null | no | | e.g. LibreOffice conversion failed |

## 3. Fields — ExportResult

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `export_id` | string | yes | prefix `exp_` | Opaque |
| `session_id` | string | yes | prefix `ses_` | |
| `draft_id` | string | yes | prefix `draft_` | |
| `kind` | ExportKind | yes | `draft` \| `final` | enum |
| `docx` | ExportArtifact | yes | | Primary deliverable |
| `pdf_preview` | ExportArtifact \| null | no | | Optional; failure must not remove DOCX |
| `preflight_id` | string | yes | prefix `preflight_` | Gate report used |
| `created_at` | datetime | yes | ISO-8601 UTC | |

## 4. Validation rules

- `kind: final` requires `PreflightReport.programmatic_gate == "pass"` and no blocking findings; otherwise API returns `export_blocked_preflight` or `export_blocked_red_issues` ([error-codes.md](../error-codes.md)) and **no** artifacts.
- `kind: draft` may allow noncritical warnings with an explicit draft label in UI; still must not claim final.
- Never expose server paths in the JSON payload.
- PDF conversion failure → `pdf_preview.status = "failed"` with warning; DOCX remains `available`.

## 5. Example JSON

```json
{
  "export_id": "exp_01JEXAMPLE0000000000000E1",
  "session_id": "ses_01JEXAMPLE000000000000000",
  "draft_id": "draft_01JEXAMPLE0000000000000A1",
  "kind": "final",
  "created_at": "2026-07-18T15:05:00Z",
  "preflight_id": "preflight_01JEXAMPLE0000000000000P1",
  "docx": {
    "artifact_id": "art_01JEXAMPLE0000000000000A1",
    "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "status": "available",
    "filename": "demand_final.docx",
    "warning": null
  },
  "pdf_preview": {
    "artifact_id": "art_01JEXAMPLE0000000000000A2",
    "content_type": "application/pdf",
    "status": "available",
    "filename": "demand_final_preview.pdf",
    "warning": null
  }
}
```

## 6. Open / additive notes

- `ExportKind` lives in [enums.md](../enums.md).
- Download via `GET /api/v1/sessions/{session_id}/exports/{export_id}` (or artifact sub-route); paths stay server-side.

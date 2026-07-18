# Entity: Document

| Field | Value |
|-------|-------|
| Spec | §7.2 / §8.2 / §8.4 |
| Owning module(s) | [02 Upload](../../modules/02-upload-validation-normalization.md), [04 Classification](../../modules/04-document-classification-and-sequencing.md) |
| contracts_version | 0.1 |

## 1. Purpose

Uploaded original and derived preview metadata for one file in a session.

## 2. Fields

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `id` | string | yes | prefix `doc_` | Opaque |
| `session_id` | string | yes | prefix `ses_` | Parent session |
| `display_name` | string | yes | non-empty | Original filename for UI only |
| `file_type` | DocumentFileType | yes | enum | |
| `content_sha256` | string | yes | 64 hex chars | Duplicate detection |
| `page_count` | int | no | `>= 0` | Set after normalize |
| `classification` | DocumentClassification | no | enum | Null until classified |
| `classification_confidence` | float | no | `0–1` | |
| `classification_reason` | string | no | | Rule/LLM rationale |
| `sequence_index` | int | no | `>= 0` | User-reorderable |
| `status` | DocumentStatus | yes | enum | |
| `exclude_from_drafting` | bool | yes | default false | |
| `treat_as_secondary_evidence` | bool | yes | default false | FR-CLS-06 for existing demands |
| `page_quality_warning_count` | int | no | `>= 0` | Aggregate |
| `error_code` | string | no | | When `rejected` |
| `error_message` | string | no | user-facing | When `rejected` |

**Server-only:** internal random filename, absolute paths to original/canonical/thumbnails.

## 3. Validation rules

- API must not expose internal paths.
- `display_name` is metadata only; never used for path construction.

## 4. Example JSON

```json
{
  "id": "doc_01JEXAMPLE000000000000001",
  "session_id": "ses_01JEXAMPLE000000000000000",
  "display_name": "police-report.pdf",
  "file_type": "pdf",
  "content_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "page_count": 4,
  "classification": "police_report",
  "classification_confidence": 0.92,
  "classification_reason": "filename + first-page heading match",
  "sequence_index": 0,
  "status": "classified",
  "exclude_from_drafting": false,
  "treat_as_secondary_evidence": false,
  "page_quality_warning_count": 0
}
```

## 5. Open / additive notes

MIME and signature details may appear on upload error objects, not necessarily on accepted `Document` records.

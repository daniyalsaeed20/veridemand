# Entity: SourceSpan

| Field | Value |
|-------|-------|
| Spec | §7.2 / §7.3 / §8.3 |
| Owning module(s) | [03 Extraction](../../modules/03-page-analysis-and-text-extraction.md), [08 Human Review](../../modules/08-human-review-and-manual-intervention.md) |
| contracts_version | 0.1 |

## 1. Purpose

Readable evidence excerpt linking one or more tokens (or a manual rectangle) for highlight and citation.

## 2. Fields

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `id` | string | yes | prefix `span_` | Opaque |
| `document_id` | string | yes | prefix `doc_` | |
| `page_number` | int | yes | `>= 1` | |
| `text` | string | yes | non-empty preferred | Excerpt shown in UI |
| `token_ids` | string[] | yes | may be empty if manual-only | |
| `polygons` | number[][][] | yes | list of normalized polygons | Multi-region ok |
| `context` | string | no | | Nearby label / section hint |
| `method` | ExtractionMethod | yes | | |
| `confidence` | float | no | `0–1` | Aggregate if multi-token |

## 3. Validation rules

- Manual spans may have empty `token_ids` but must have at least one polygon.
- Every `token_id` must exist in session for the same document/page when non-empty.

## 4. Example JSON

```json
{
  "id": "span_01JEXAMPLE0000000000000B1",
  "document_id": "doc_01JEXAMPLE000000000000001",
  "page_number": 1,
  "text": "Date of Loss: 03/28/2026",
  "token_ids": ["tok_01JEXAMPLE0000000000000A1"],
  "polygons": [[[0.10, 0.20], [0.40, 0.20], [0.40, 0.25], [0.10, 0.25]]],
  "context": "collision report header",
  "method": "ocr",
  "confidence": 0.97
}
```

## 5. Open / additive notes

Viewer highlight uses `polygons` at any zoom via §7.3 display transform.

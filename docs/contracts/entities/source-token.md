# Entity: SourceToken

| Field | Value |
|-------|-------|
| Spec | §7.2 / §7.3 / §8.3 |
| Owning module(s) | [03 Page Analysis and Text Extraction](../../modules/03-page-analysis-and-text-extraction.md) |
| contracts_version | 0.1 |

## 1. Purpose

Smallest positioned text unit from native extraction or OCR.

## 2. Fields

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `id` | string | yes | prefix `tok_` | Opaque |
| `document_id` | string | yes | prefix `doc_` | |
| `page_number` | int | yes | `>= 1` | |
| `text` | string | yes | may be empty only if flagged | |
| `confidence` | float | yes | `0–1` | Native may be `1.0` |
| `polygon` | number[][] | yes | normalized `[x,y]` points in `[0,1]` | Quad or more |
| `method` | ExtractionMethod | yes | `native` \| `ocr` \| `manual` | |

## 3. Validation rules

- All polygon coordinates must be in `[0, 1]`.
- Reject tokens that include absolute pixel-only geometry without normalization.

## 4. Example JSON

```json
{
  "id": "tok_01JEXAMPLE0000000000000A1",
  "document_id": "doc_01JEXAMPLE000000000000001",
  "page_number": 1,
  "text": "03/28/2026",
  "confidence": 0.98,
  "polygon": [[0.12, 0.22], [0.25, 0.22], [0.25, 0.24], [0.12, 0.24]],
  "method": "ocr"
}
```

## 5. Open / additive notes

Optional `line_index` / `block_index` may be added later for reading-order helpers.

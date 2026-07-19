# Entity: DocumentPage

| Field | Value |
|-------|-------|
| Spec | §7.2 / §8.3 / §9 |
| Owning module(s) | [03 Page Analysis and Text Extraction](../../modules/03-page-analysis-and-text-extraction.md) |
| contracts_version | 0.1 |

## 1. Purpose

Page-level extraction quality and routing for one page of a document.

## 2. Fields

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `id` | string | yes | opaque; may be `page_{doc}_{n}` | |
| `document_id` | string | yes | prefix `doc_` | |
| `page_number` | int | yes | `>= 1` | 1-based |
| `width` | float | yes | `> 0` | Source page units before normalize |
| `height` | float | yes | `> 0` | |
| `text_coverage` | float | no | `0–1` | Native/OCR coverage heuristic |
| `route` | PageRoute | yes | enum | native / ocr / manual_review |
| `ocr_status` | OcrStatus | no | `not_needed` \| `pending` \| `done` \| `failed` | Closed vocabulary |
| `extraction_method` | ExtractionMethod | no | primary method used | |
| `quality_flags` | string[] | yes | default `[]` | Additive codes e.g. `blank`, `broken_text_layer`, `pathological_tokenization`, `awaiting_ocr`, `low_confidence`, `suspected_handwriting` |
| `token_count` | int | no | `>= 0` | |
| `span_count` | int | no | `>= 0` | |

## 3. Validation rules

- `page_number` unique per `document_id`.
- Quality flags never silently drop evidence; they create review visibility.

## 4. Example JSON

```json
{
  "id": "page_doc_01JEXAMPLE000000000000001_1",
  "document_id": "doc_01JEXAMPLE000000000000001",
  "page_number": 1,
  "width": 2550,
  "height": 3300,
  "text_coverage": 0.12,
  "route": "ocr",
  "ocr_status": "done",
  "extraction_method": "ocr",
  "quality_flags": [],
  "token_count": 840,
  "span_count": 120
}
```

## 5. Open / additive notes

Exact `quality_flags` vocabulary may grow; treat as additive string codes.

Known Phase 2/3 additive codes:

- `blank` — no native words
- `broken_text_layer` — encoding/geometry/printable failures
- `pathological_tokenization` — multi-signal unusable native tokenization (suppress tokens/spans; await OCR)
- `awaiting_ocr` — page routed for OCR (cleared after OCR commit)
- `low_confidence` — OCR usable-with-warning or low mean confidence
- `duplicate_detections` / `duplicate_page` — overlapping or duplicated OCR detections
- `suspected_handwriting` — handwriting heuristic (review; not authoritative OCR)

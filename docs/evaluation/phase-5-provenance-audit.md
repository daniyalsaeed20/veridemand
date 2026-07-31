# Phase 5 candidate-source provenance audit

**Verdict:** `correct`

Audit version: `phase5-provenance-audit-v1`
Generated (UTC): `2026-07-31T06:43:51.308739+00:00`

## Aggregate evidence

- Documents: **6**
- Source groups: **6**
- Unique page IDs: **215**
- Source-manifest rows: **215**
- Source-manifest duplicate rows: **0**
- Crop records: **65649**
- Canonical crops: **44951**
- Evidence lines: **17929**
- Evidence blocks: **17929**
- Evidence words: **56832**
- Evidence repair regions: **0**
- Pages with 1:1 block=line proxies: **215**

## Candidate-source categories

| category | records | canonical | groups | pages | excluded | status |
|---|---:|---:|---:|---:|---:|---|
| `full_page_ocr` | 65649 | 44951 | 6 | 215 | 0 | `assigned` |
| `heuristic_region` | 0 | 0 | 0 | 0 | 0 | `absent_from_private_evidence` |
| `manual_region` | 0 | 0 | 0 | 0 | 0 | `absent_from_private_evidence` |
| `noise_region` | 0 | 0 | 0 | 0 | 0 | `absent_from_private_evidence` |
| `synthetic_negative` | 0 | 0 | 0 | 0 | 0 | `absent_from_private_evidence` |
| `targeted_repair` | 0 | 0 | 0 | 0 | 0 | `absent_from_private_evidence` |
| `visual_detection` | 0 | 0 | 0 | 0 | 17929 | `excluded_as_line_proxy` |

## Notes

Private populate writes OCR line/word geometry with empty repair_regions and 1:1 block proxies copied from lines. Batch export uses kinds={lines, repair_regions} so all crops are full_page_ocr. This is correct provenance, not a collapse of distinct Phase 4 visual/repair categories into full_page_ocr.

Candidate provenance is selection metadata only and must never be treated as a script label or shown to primary/secondary crop reviewers.

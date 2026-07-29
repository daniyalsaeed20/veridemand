# Phase 4 — Printed OCR quality gate (Correction 5)

## Purpose

Dense printed forms (ruling lines, checkboxes, isolated field numbers, small
type) often produce a fragmented fast primary OCR pass at detector side 960.
Mean recognition confidence alone cannot decide whether that result is usable.

Correction 5 introduces a single typed evidence model and a versioned primary-pass
quality gate that can trigger exactly one higher-resolution fallback (1600) and
then select the better validated result.

## Score directions

| Metric | Higher means |
|--------|----------------|
| `fragmentation_score` | Worse (more suspected fragmentation) |
| `over_segmentation_score` | Worse |
| `box_overlap_ratio` / `near_duplicate_box_ratio` | Worse |
| `grid_intersection_ratio` | More boxes touch ruling lines (signal) |
| `text_coverage_ratio` | Better coverage of page by OCR geometry |
| `geometry_valid_ratio` | Better |
| `out_of_bounds_ratio` | Worse |
| `low_confidence_ratio` | Worse |
| `single_character_*` / `symbol_only_*` | Worse noise |
| `mean_confidence` / `median_confidence` | Recognition confidence only — **not accuracy** |

## Pipeline

1. `full_ocr_primary` — detector side 960 (when fast-pass enabled)
2. Cheap `page_profile` (dense_form / ordinary / sparse / …) from visual signals
3. `full_ocr_quality_evaluation` — build `PrintedOcrQualityEvidence`, apply profile gate
4. If gate fails → exactly one sequential `full_ocr_fallback` at 1600
5. `full_ocr_result_selection` — `OcrPassComparison` keep-better selection
6. Provisional noise classification + line grouping on the **selected** pass only
7. Publish selected word/line boxes with `ocr_pass` provenance

## Handwriting boundary

Handwriting is never claimed as printed text. Regions that look non-printed are
classified `handwriting_candidate_pending_phase_5`. Page-level
`handwriting_assessment` remains `pending_phase_5`.

## Privacy

Logs and acceptance reports never include OCR strings, private filenames, paths,
or page images — only aggregates and reason codes.

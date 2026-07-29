# ADR 0034 — Adaptive primary/fallback printed OCR

## Status

Accepted (Correction 5)

## Context

Fast primary OCR at detector side 960 is adequate for ordinary pages but often
produces fragmented output on dense printed forms. The previous adequacy check
(min detections / mean confidence / coarse coverage) accepted fragmented dense
forms and overwrote primary results when fallback ran.

## Decision

1. Run primary at configured `ocr_primary_limit_side_len` (960).
2. Evaluate quality with `PrintedOcrQualityEvidence` (ADR 0035).
3. If the primary quality gate fails, run exactly one sequential fallback at
   `ocr_fallback_limit_side_len` (1600) within existing page deadlines.
4. Select the better validated pass via `OcrPassComparison`; never merge
   transcripts; never select solely because the image is larger.
5. Publish only the selected pass boxes.

## Consequences

- Dense forms may take longer when fallback runs; timeouts are not raised.
- Progress exposes `full_ocr_quality_evaluation` and `full_ocr_result_selection`.

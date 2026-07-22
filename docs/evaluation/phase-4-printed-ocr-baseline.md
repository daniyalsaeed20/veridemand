# Phase 4 printed OCR baseline (synthetic calibration)

## Purpose

Record CER/WER/IoU **calibration** notes for local PP-OCRv6 printed OCR on
`fixtures/synthetic/ocr/`. This is **not** firm-approved gold and does not claim
general OCR accuracy.

## Stack

| Item | Value |
|------|-------|
| paddleocr | 3.7.0 |
| paddlepaddle | 3.3.0 (CPU) |
| Detector | PP-OCRv6_medium_det |
| Recogniser | PP-OCRv6_medium_rec |
| Render DPI | 200 (ADR 0018) |
| Device | cpu |

## Measured (local Windows CPU, 2026-07-23)

From `pnpm evaluate:ocr` (opaque aggregates; hypothesis text omitted):

| Metric | Value |
|--------|-------|
| Cases | 12 (11 evaluated, 1 Phase-5 skip) |
| Clean mean CER | 0.009 |
| Degraded mean CER | 0.000 |
| Gate result | pass |

Notable: `two_columns` measured CER 0.063 / WER 0.25 on clean gate (pulls mean CER
up but overall gate still passed). Empty page correctly produced zero lines.

## Suggested gates (calibration)

| Gate | Threshold |
|------|-----------|
| Clean synthetic printed pages | CER ≤ 0.03 (mean) |
| Moderately degraded pages | CER ≤ 0.15 |
| Known line polygons (when provided) | median IoU ≥ 0.70 |

Do not weaken production OCR thresholds solely to pass one fixture.

## How to run

```bash
pnpm models:ocr:bootstrap
pnpm models:ocr:verify
pnpm evaluate:ocr
```

Reports omit hypothesis/reference text. Handwriting fixtures are
`phase5_pending` and skipped.

## Private corpus

Use gitignored `fixtures/private/visual-ocr-manifest.local.json` and
`scripts/evaluate_private_visual_ocr.py` for opaque aggregates only.

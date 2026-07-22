# ADR 0018 — Local PaddleOCR inference (PP-OCRv6)

## Status

Accepted (Phase 4)

## Context

The Source of Truth initially named PP-OCRv5. Product calibration on this
repository selected **PP-OCRv6 medium** detection and recognition for printed
text. Rendering for OCR uses DPI **200** (see ADR 0017). The SoT is **not**
rewritten; this ADR records the calibrated implementation choice.

## Decision

- Run **local** printed OCR only: `paddleocr==3.7.0` + `paddlepaddle==3.3.0`
  (CPU), optional `ocr` dependency group.
- Models: `PP-OCRv6_medium_det` and `PP-OCRv6_medium_rec`, bootstrapped into
  `.models/paddleocr/` (gitignored) with `model-record.json`.
- Default device: CPU. No cloud OCR tokens. No handwriting classifiers. No
  vision-LLM calls in Phase 4.
- Progress after printed visual OCR is capped at **65%**.

## Consequences

Operators must bootstrap models once (`pnpm models:ocr:bootstrap`). CI caches
model trees by OS/Python/Paddle/model names. GPU is unsupported in Phase 4
baseline evidence.

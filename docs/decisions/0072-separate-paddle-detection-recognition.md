# ADR 0072 — Separate Paddle detection and recognition

## Status

Accepted (Phase 5 Task C0)

## Context

Phase 4 uses a combined `PaddleOCR.predict` pipeline. Phase 5 routing requires
detector-owned regions before printed recognition. Combined prediction drops
empty-recognition boxes and cannot classify before recognise.

## Decision

Expose explicit offline APIs via PaddleX `create_model` against the same
configured local model directories (`PP-OCRv5_mobile_det` /
`PP-OCRv5_mobile_rec` by Settings default):

- `detect_text` — detection only
- `recognise_text_crops` — recognition of supplied crops only (no redetect)

Do not switch model families silently. Do not replace the live combined path in
Task C0.

## Consequences

Shadow/offline tooling can build a detector-first corpus. Live worker behaviour
remains Phase 4 combined OCR until a later gated integration task.

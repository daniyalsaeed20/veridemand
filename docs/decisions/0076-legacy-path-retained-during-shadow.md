# ADR 0076 — Legacy combined OCR path retained during shadow evaluation

## Status

Accepted (Phase 5 Task C0)

## Context

Splitting detection from recognition is a prerequisite for Phase 5 routing, but
live replacement without equivalence evidence would risk Phase 4 printed OCR
quality, progress, and scheduling contracts.

## Decision

- Keep the combined `PaddleOCR.predict` path as the only live worker OCR path.
- Gate detector-first modules behind `PHASE5_DETECT_FIRST_SHADOW_ENABLED=false`
  and explicit offline commands.
- Do not invoke the handwriting classifier from OCR paths in Task C0.
- Progress remains capped at 65%; fair scheduling and page routes unchanged.

## Consequences

Task C0 can validate adapters and build a private corpus without changing
document results. Live detect→classify→recognise integration is deferred to a
later task after recognition equivalence and router retraining.

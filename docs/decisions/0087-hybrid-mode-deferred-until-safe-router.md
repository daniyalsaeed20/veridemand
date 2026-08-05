# ADR 0087 — Hybrid page OCR deferred until a safe region router exists

## Status

Accepted (Phase 5 Task C3) — **current Phase 5 release architecture** (hybrid remains deferred / rejected until a safe region router exists).

## Context

Hybrid page reservation would retain local printed OCR on reserved pages while
still covering detector-missed ink at page scope. That path requires a region
router that blocks handwritten and uncertain detections from Paddle.

## Decision

Do not implement hybrid mode in Task C3. Keep mode validation rejecting `hybrid`.
Revisit only after a region router passes the zero-leakage and printed-retention
gates.

## Consequences

- Conservative reservation is the only live fallback.
- Classifier retraining and hybrid wiring are not automatic follow-ons from C3.

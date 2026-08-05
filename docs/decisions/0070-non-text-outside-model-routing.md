# ADR 0070 — Non-text kept outside model public routing decision

## Status

Accepted (Phase 5 Task B4)

## Context

Task B3 allowed the dual-risk policy to emit `non_text` from the model. That
created a failure mode where handwriting could be discarded as non-text, and
conflated Phase 4 geometry/noise suppression with the Phase 5 OCR-authorisation
gate.

## Decision

The route-first decision policy returns only `printed`, `handwritten`, or
`uncertain`. The model never emits `non_text`. Known non-text continues to be
suppressed by existing Phase 4 logic. Uncaught non-text-like crops that the
model rejects must become `uncertain` (reserved) rather than `printed`.

Non-text remains a human training label with `vision_required=1` and
`handwriting_present=0` so unsafe crops are not authorised for Paddle.

## Consequences

Public API outcomes still include `non_text` for Phase 4 paths. Routing-matrix
columns retain `non_text` for evaluation of Phase 4-origin outcomes, but model
policy counts for that column stay zero. Non-text → printed must remain zero.

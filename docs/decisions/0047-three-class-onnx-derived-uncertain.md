# ADR 0047 — Three-class ONNX output with derived uncertainty

## Status

Accepted (Phase 5 Task 2)

## Context

Phase 5 must expose public routing outcomes `printed`, `handwritten`,
`uncertain`, and `non_text`. The repository has no human-labelled ambiguous
crop set that could support a reliable learned `uncertain` class.

## Decision

The ONNX model outputs three classes only:

- `printed`
- `handwritten`
- `non_text`

Public `uncertain` is produced by deterministic runtime abstention (threshold
miss, low margin, collision, invalid I/O, unavailable/failed classifier under
enforced mode). Do not add `uncertain` as a fourth ONNX output class in the
initial Phase 5 implementation.

## Consequences

Routing safety prefers abstention over false `printed`. Threshold calibration
and held-out evaluation remain later tasks. Contracts separate lifecycle from
outcome so `uncertain` is never confused with `not_run` / `unavailable` /
`failed`.

# ADR 0078 — Bounded detector-parameter calibration

## Status

Accepted (Phase 5 Task C1)

## Context

PaddleX text detection exposes predict-time knobs (`thresh`, `box_thresh`,
`unclip_ratio`, `limit_side_len`, `limit_type`). An unbounded search would be
non-reproducible and could select pathological full-page boxes.

Task C0 called detect without kwargs (model YAML intrinsic defaults). Phase 4
Settings defaults differ (notably `limit_side_len=1600`) and must be treated as
an explicit calibrated variant when applied to shadow detect-first.

## Decision

- Cap materially different configs at 12 (`phase5-detector-calibration-v1`).
- Reject invalid thresholds and near-full-page boxes.
- Use deterministic configuration IDs.
- Prefer recall of known handwriting seeds over maximising raw box count.

## Consequences

Calibration remains offline/shadow only. Live Settings and combined OCR path
are not changed by Task C1.

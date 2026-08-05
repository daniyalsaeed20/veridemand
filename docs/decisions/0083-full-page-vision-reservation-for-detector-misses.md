# ADR 0083 — Full-page vision reservation covers detector misses

## Status

Accepted (Phase 5 Task C3)

## Context

Task C1 best detector candidate still missed seven known handwriting regions
(mostly signatures). Any region classifier can only act on detected crops.

## Decision

Conservative page reservation retains the full page with normalised geometry
`[0, 0, 1, 1]` so undetected handwriting remains available for Phase 6 vision
processing. No invented region coordinates are fabricated.

## Consequences

- Detector misses on reserved pages cannot leak into Paddle (recognition is skipped).
- Phase 6 may re-render from the session-owned canonical PDF; no PNG contact sheets.

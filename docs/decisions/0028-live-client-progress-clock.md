# 0028 — Live client progress clock

## Status

Accepted

## Context

Elapsed/ETA only updated when SSE events arrived, so long Paddle calls looked
frozen.

## Decision

One shared frontend ticker projects elapsed and remaining from the latest
backend snapshot without sending per-second SSE events.

## Consequences

UI stays responsive; viewer isolation is required so PDF.js does not rerender
every second.

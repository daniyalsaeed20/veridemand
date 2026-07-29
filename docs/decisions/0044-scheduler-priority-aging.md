# 0044 — Scheduler priority aging

## Status

Accepted

## Context

Continual arrival of small documents could starve a large document indefinitely
under strict priority-class ordering.

## Decision

Bounded priority aging: a waiting document's effective priority increases every
SCHEDULER_AGING_INTERVAL_SECONDS. Combined with SCHEDULER_MAX_CONSECUTIVE_TURNS,
this ensures every ready document eventually runs.

## Consequences

No indefinite starvation. Large documents may experience longer waits but are
guaranteed progress. Aging parameters are configurable.

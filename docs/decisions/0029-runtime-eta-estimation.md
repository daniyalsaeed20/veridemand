# 0029 — Runtime ETA estimation

## Status

Accepted

## Context

A single average for all page types mis-estimates mixed native/OCR workloads.

## Decision

Runtime-only, route-aware ETA using robust statistics. Statuses include
unavailable, collecting_samples, available, recalculating, stale, complete.
Never persist user-document performance data.

## Consequences

ETA is authoritative from the backend; the client only projects the countdown.

# ADR 0032 — Monotonic backend and frontend clocks

## Status

Accepted (Correction 4)

## Context

Elapsed labels mixed batch and document time; wall-clock subtraction was
unreliable.

## Decision

Backend durations use monotonic clocks per batch/document/phase/page/operation/
attempt. The frontend keeps one shared ticker and interpolates from snapshot
baselines. Hidden tabs pause display ticks only.

## Consequences

UI labels distinguish Batch / Current document / phase / page / operation
elapsed. Timer ticks never remount the viewer or append timeline rows.

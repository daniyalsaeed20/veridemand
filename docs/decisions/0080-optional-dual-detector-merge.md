# ADR 0080 — Optional dual-detector merge (shadow)

## Status

Accepted (Phase 5 Task C1)

Shadow merge only; **best incomplete recall still failed zero-miss** (7 misses).

## Context

Mobile and server detectors may cover complementary handwriting regions.
Naïve union creates duplicate crops; collapsing to the larger box can discard
tighter handwriting geometry.

## Decision

Introduce versioned offline merge `phase5-dual-detector-merge-v1`:

- Merge exact / high-IoU equivalents with retained provenance and both
  confidences.
- Keep neighbouring non-overlapping lines separate.
- Retain partial-overlap fragments for coverage analysis.
- Emit stable deterministic merged region IDs.

Dual merge runs only in calibration tooling — not in the live worker.

## Consequences

Merged candidates can compete in the known-seed gate. When quality is equal,
prefer simpler mobile-only deployment over dual-detector.

# 0040 — Retained / repaired result reconciliation

## Status

Accepted

## Context

Targeted repair must not rewrite the whole page or concatenate transcripts
blindly.

## Decision

Classify base items as retained, suppressed_for_repair, overlaps_repair_region,
quarantined, or unaffected. Suppress only material overlaps or explicit failed
candidates. Reconcile spatially: prefer repaired output inside repair regions,
preserve retained output outside, assign stable IDs, keep provenance, validate
geometry, and rebuild provisional lines.

## Consequences

Public pages expose aggregate retained/repaired/suppressed/region counts.
Quarantined candidate strings are never published.

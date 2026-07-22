# ADR 0021 — Provisional visual reading order

## Status

Accepted (Phase 4)

## Context

OCR detection order is not a reliable reading order. Final document structure
and table semantics are later phases.

## Decision

Phase 4 publishes a **provisional** geometric column reading order
(`geometric_columns_phase_4` / `provisional_phase_4`). Layout grouping produces
`text_unknown` blocks only — no header/table/list semantic labels.

UI must label reading order as preliminary. Handwriting assessment remains
`pending_phase_5`.

## Consequences

Consumers must not treat Phase 4 line order as final structure. Smoke cases for
final reading-order / table structure stay skipped.

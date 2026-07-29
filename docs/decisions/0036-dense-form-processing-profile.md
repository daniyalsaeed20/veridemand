# ADR 0036 — Dense-form processing profile

## Status

Accepted (Correction 5)

## Context

Dense forms need stricter fast-pass acceptance than sparse letters. Filename or
hash based routing is forbidden.

## Decision

Classify pages with inexpensive visual/structural signals into
`PageProcessingProfile` values (`ordinary_document`, `dense_form`, `table_like`,
`sparse_document`, `photo_with_text`). Dense forms use stricter fragmentation,
single-character, and symbol thresholds. Sparse pages are not rejected merely
for low line count.

Profile selection is a processing-policy signal only — not semantic form field
identification.

## Consequences

- Profile reason codes appear on page results and privacy-safe logs.
- Police / billing field semantics remain out of scope.

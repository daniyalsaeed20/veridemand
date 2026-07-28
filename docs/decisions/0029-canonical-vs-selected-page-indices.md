# ADR 0029 — Canonical document page vs selected-work indices

## Status

Accepted (Correction 4)

## Context

Progress payloads mixed absolute document page numbers with selected visual-page
counts (e.g. page 20 of 2), producing contradictory UI labels.

## Decision

Publish explicit fields: `document_page_number` / `document_pages_total` and
`selected_page_index` / `selected_pages_total` (plus visual/route variants).
Legacy `page_number` means document page; legacy `pages_total` means selected
count and must not be paired in new UI.

## Consequences

Contracts, coordinator publish paths, and frontend labels use the explicit
fields. Validators enforce index ≤ total.

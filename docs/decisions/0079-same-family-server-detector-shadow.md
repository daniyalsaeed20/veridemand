# ADR 0079 — Same-family server detector shadow comparison

## Status

Accepted (Phase 5 Task C1)

Shadow comparison only; **insufficient for zero-miss gate**; live mobile detector unchanged.

## Context

PP-OCRv5 includes an official server detector that may improve handwriting
region recall versus the mobile detector used in Phase 4. Silently replacing
the live detector would violate ADR 0072 and risk printed OCR quality.

## Decision

- Evaluate `PP-OCRv5_server_det` offline only via explicit bootstrap
  (`pnpm models:ocr:bootstrap:server-det`).
- Store assets under the gitignored OCR model root; record hash/size/provenance
  in `model-record.json` without replacing the live mobile detector name.
- Never initialise the server detector from the normal worker path.

## Consequences

Server comparison evidence can inform a future candidate without changing
Phase 4 uploads. Model binaries remain uncommitted.

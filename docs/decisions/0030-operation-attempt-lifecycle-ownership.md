# ADR 0030 — Operation-attempt lifecycle ownership

## Status

Accepted (Correction 4)

## Context

Duplicate and out-of-order operation events (selection, OCR completion,
publication) confused timelines and ETA.

## Decision

`ProcessingCoordinator` owns all public lifecycle transitions. An
`OperationLifecycleLedger` enforces queued ≤ 1, started = 1, terminal ≤ 1 per
attempt identity. Workers and visual services remain diagnostic-only for public
stage events. Retries mint a new attempt identity.

## Consequences

Duplicate terminals are suppressed with privacy-safe diagnostics. Telemetry
failures never abort extraction.

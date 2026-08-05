# ADR 0084 — Conservative mode because the region router is not safe

## Status

Accepted (Phase 5 Task C3) — **current Phase 5 release architecture** (feature default off).

## Context

Task C2 recommended hybrid reservation plus a region router if the router can
block handwritten and uncertain regions from Paddle. Tasks B–B4 failed to produce
a router that simultaneously achieved zero handwriting leakage and ≥80% printed
retention.

## Decision

Task C3 implements **conservative** mode only (`HANDWRITING_PAGE_VISION_FALLBACK_MODE=conservative`).
Unsupported modes such as `hybrid` are rejected loudly.

## Consequences

- Reserved pages run no local recognition.
- Hybrid mode remains deferred until a safe region router exists (ADR 0087).

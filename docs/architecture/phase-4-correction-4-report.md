# Correction 4 implementation report (sanitised)

## Scope

Progress events, page semantics, live clocks/deadlines, slow warnings, and ETA
consistency. No Phase 5 work. No native-trust, routing, or OCR quality changes.
Stash `wip-phase44-throughput` untouched.

## Evidence (synthetic)

- Backend lifecycle tests: page identity distinct; one terminal per attempt;
  heartbeat does not advance overall; overall capped at 65; sparse OCR uses
  selected fraction; deadlines separated; slow warning resets on new operation.
- Frontend reducer rejects stale sequence/version and terminal→active regression.
- Shared ticker pauses when hidden; remaining never negative.
- Contracts regenerated; OpenAPI/Zod drift check required in CI.

## Private acceptance (local only — no text/paths in this report)

Deferred to operator run against opaque acceptance aliases after CI green:

- police scan: two full-OCR pages; labels; no duplicate lifecycle
- billing: native ×7 / OCR ×2
- text-rich: native ×97 / OCR ×0

## Phase boundary

Correction 4 only. No new Phase 4 completion tag.

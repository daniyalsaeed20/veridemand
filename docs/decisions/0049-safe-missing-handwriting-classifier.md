# ADR 0049 — Safe disabled / missing / broken handwriting classifier

## Status

Accepted (Phase 5 Task 2)

## Context

Enabling classification before a verified model exists must not silently treat
regions as printed or break Phase 4 by default.

## Decision

- `handwriting_router_enabled=false` (default): Phase 4 unchanged; health
  `not_configured`; no ONNX session.
- Enabled + optional + broken: health check `fail` with `required=false`;
  `/health/ready` may remain ready; enforced classification returns lifecycle
  `unavailable`/`failed` with outcome `uncertain`.
- Enabled + required + broken: `/health/ready` fails; liveness unaffected.
- Reject `handwriting_classifier_required=true` when the router is disabled.
- Never default invalid/missing classifier output to `printed`.

Live OCR wiring remains Task 4. Task 2 only establishes the service and health
policy.

## Consequences

Operators can ship Phase 4 safely with the router off. Acceptance profiles may
later enable/require the classifier once a production-candidate package exists.

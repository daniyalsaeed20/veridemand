# ADR 0085 — vision_reserved_pending_phase_6 exclusive page route

## Status

Accepted (Phase 5 Task C3) — **current Phase 5 release architecture** (feature default off).

## Context

Phase 4 exclusive `FinalRouteHistogram` accounting requires every page to
contribute to exactly one terminal bucket.

## Decision

Add exclusive terminal route / page-result state
`vision_reserved_pending_phase_6`. Reserved pages must not also be counted under
digital-native, embedded OCR, full visual OCR, visual-no-text, failed, or
cancelled buckets.

## Consequences

- Histogram sum assertions include the new bucket.
- UI route breakdown shows “Reserved for vision processing”.
- Feature-off Phase 4 histograms remain unchanged.

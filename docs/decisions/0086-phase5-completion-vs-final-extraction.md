# ADR 0086 — Phase 5 completion versus final extraction completion

## Status

Accepted (Phase 5 Task C3) — **current Phase 5 release architecture** (feature default off).

## Context

Documents with reserved pages finish local Phase 5 reservation work without
final extraction. Progress remains capped at 65%.

## Decision

Introduce document lifecycle `awaiting_phase_6` meaning Phase 5 reservation is
complete but final extraction is not. It is not failure and not extraction
success. Progress may reach the 65% ceiling while status remains
`awaiting_phase_6`. Phase 6 owns the exit transition.

## Consequences

- Public API and SSE distinguish local completion from awaiting vision.
- Frontend shows “Awaiting vision extraction”, never “Completed” / provider names.
- `result_available` and `extraction_performed` remain false.

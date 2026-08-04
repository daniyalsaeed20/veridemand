# ADR 0057 — Prototype threshold safety gates

## Status

Accepted (Phase 5 Task B)

## Context

The classifier emits three probabilities; public `uncertain` is derived by the
existing abstention rules (`decide_routing_outcome`). Provisional settings
defaults are not calibrated. Task B must select prototype thresholds from
source-group-isolated OOF predictions without enabling live routing.

## Decision

1. Search a bounded grid over
   `printed_threshold`, `handwriting_threshold`, `non_text_threshold`, and
   `minimum_class_margin`.
2. Optimise lexicographically:
   1. minimise handwritten → printed;
   2. minimise non_text → printed;
   3. maximise handwriting safe-bypass recall (handwritten ∨ uncertain);
   4. maximise printed retention recall;
   5. minimise unnecessary uncertainty.
3. Task B prototype safety gate (engineering, not release):
   - handwritten routed printed = 0;
   - handwriting safe-bypass recall = 100%;
   - non_text routed printed = 0;
   - printed retention recall ≥ 80%.
4. Do not lower the gate to pass. Do not enable `handwriting_router_enabled`.
5. Leave settings defaults unchanged for Task C to load calibrated values
   explicitly.

## Consequences

- A trivial all-uncertain router fails printed retention.
- Threshold values are recorded in package notes / evaluation docs under
  `threshold_set_version` (e.g. `phase5-task-b-prototype-v1`).
- Task D remains responsible for integrated release evaluation.

## Related

- ADR 0047 (derived uncertainty)
- ADR 0049 (safe disabled/missing classifier)

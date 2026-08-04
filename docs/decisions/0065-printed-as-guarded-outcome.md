# ADR 0065 — Printed as a guarded outcome

## Status

Accepted (Phase 5 Task B3)

## Context

Under three-class softmax, `printed` was a model class that often won by
default when handwriting evidence was weak but non-zero. Sending that region
to Paddle recognition is the Phase 5 safety failure mode.

## Decision

1. Do not emit a printed logit from the model.
2. Grant public `printed` only when both independent risks are safely low:

   ```text
   p_hw <= handwriting_safe_low_threshold
   and
   p_nt <= non_text_safe_low_threshold
   ```

3. Printed is therefore a positively guarded safe-local-recognition decision,
   not the default outcome.
4. When in doubt, abstain as `uncertain` (never default to printed).

## Consequences

Printed retention becomes a coverage metric under an explicit safety floor.
Models that reserve everything as uncertain fail the ≥80% printed-retention
gate and cannot be packaged as `production_candidate`.

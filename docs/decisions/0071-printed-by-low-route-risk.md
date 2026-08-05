# ADR 0071 — Printed granted only by low route-risk threshold

## Status

Accepted (Phase 5 Task B4)

## Context

Under three-class softmax, `printed` often won by default when handwriting
evidence was weak. Dual-risk improved guarding but still used two safe-low
thresholds. Printed must never be the default abstention outcome.

## Decision

Public policy:

```text
if invalid: uncertain
elif p_route <= local_ocr_safe_threshold: printed
elif p_route >= vision_required_threshold and p_hw >= handwriting_accept_threshold:
    handwritten
else: uncertain
```

Require `local_ocr_safe_threshold < vision_required_threshold`. Printed is
granted only when route risk is safely low. Grey-zone and route-positive /
handwriting-low cases abstain as uncertain.

Lexicographic gates (project OOF): HW→printed, uncertain→printed,
non_text→printed, cursive→printed, signature→printed all zero; printed
retention ≥ 80%; then maximise direct handwritten and minimise unnecessary
uncertainty. Safe-bypass for handwritten and uncertain must be 100%.

## Consequences

Settings expose the three route-first thresholds. Dual-risk env knobs are
retired. Packages embed calibrated thresholds only when every gate passes.

# ADR 0063 — Safety-first dual-risk classifier

## Status

Accepted (Phase 5 Task B3)

**Failed baseline — superseded for the current release path** by ADRs 0068–0071 (also failed) and ADRs 0082–0087. No `production_candidate` shipped (SAFETY-FIRST MODEL STILL NOT SAFE).

## Context

Task B and Task B2 trained a forced three-class softmax over
`printed` / `handwritten` / `non_text`. That mutual-exclusion objective could
not meet the prototype routing safety gates: handwriting leaks into printed or
non_text still occurred whenever printed retention stayed above 80%.

Phase 5 requires that handwriting and uncertainty never enter Paddle
recognition. False printed (and false non_text discard of handwriting) are
safety-critical; false uncertain / handwritten for printed crops are coverage
costs only.

## Decision

1. Replace the three-class softmax training objective with a shared-backbone
   dual-risk classifier that independently estimates handwriting risk and
   non-text risk.
2. Derive public outcomes `printed` / `handwritten` / `uncertain` / `non_text`
   through a deterministic safety-first abstention policy (ADR 0066).
3. Mark the Task B / B2 three-class design as
   **prototype baseline — superseded for safety evaluation** (not a coding
   failure). Preserve all prior diagnostics and ADRs.
4. Export an ONNX production candidate only if all Task B3 project safety
   gates pass.

## Consequences

Training, threshold search, package schema, and runtime interpretation move to
independent binary risk logits. Public lifecycle / outcome contracts remain
unchanged. Live OCR integration and router enablement remain later tasks.

# ADR 0064 — Independent handwriting and non-text logits

## Status

Accepted (Phase 5 Task B3)

## Context

A single mutually exclusive softmax forces one class to win even when evidence
conflicts (for example both handwriting-like strokes and form-rule clutter).
That conflict is better expressed as two independent risks.

## Decision

1. ONNX output name: `risk_logits`, shape `[batch, 2]`.
2. Index 0: `handwriting_risk_logit`; index 1: `non_text_risk_logit`.
3. Apply independent sigmoid; never softmax across the two heads.
4. Training targets:

   | Human class | handwriting | non-text |
   | ----------- | ----------: | -------: |
   | printed     |           0 |        0 |
   | handwritten |           1 |        0 |
   | non_text    |           0 |        1 |

5. Do not train on `uncertain` (challenge set only).
6. Compare at most three bounded loss configs: weighted BCE, asymmetric HW-FN
   weighted BCE, and binary focal loss (Torch primitives only).

## Consequences

Package `labels.json` declares risk outputs separately from public outcomes.
Runtime and threshold search operate on independent probabilities
`p_hw` and `p_nt`.

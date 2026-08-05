# ADR 0068 — Route-first safety objective

## Status

Accepted (Phase 5 Task B4)

**Failed baseline — rejected for the current release path** (region router unshipped). Release architecture is ADRs 0082–0087. No `production_candidate` shipped (ROUTE-FIRST MODEL STILL NOT SAFE).

## Context

Task B / B2 three-class softmax and Task B3 dual-risk
(`handwriting_risk` / `non_text_risk`) could not simultaneously achieve zero
handwriting leakage and printed retention ≥ 80%. Dual-risk still optimised a
proxy (style risks) rather than the business question: whether a crop may enter
local Paddle recognition.

## Decision

Train a shared MobileNetV3-Small backbone with two independent sigmoid heads:

1. `vision_required` — primary safety head: must this crop stay away from Paddle?
2. `handwriting_present` — secondary head: supports handwritten vs uncertain

Only `vision_required` may authorise or reject local OCR. The handwriting head
never grants Paddle permission. ONNX output is `route_logits` `[batch, 2]` with
`output_semantics=route_first_independent_logits` (schema v3). Softmax is
forbidden.

## Consequences

Task B / B2 / B3 remain valid failed baselines (ADRs 0054–0067). Production
packages use schema v3. Router stays disabled until gates pass and a later
integration task wires OCR.

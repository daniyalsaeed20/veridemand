# Phase 5 classifier prototype evaluation

**Status:** `SAFETY-FIRST MODEL STILL NOT SAFE`

**Diagnostics kind:** source-group-isolated out-of-fold prototype diagnostics  
(not final release held-out metrics)

## Three-class forced softmax baseline versus dual-risk safety-first router

| Era | Objective | Decision |
|-----|-----------|----------|
| Task B | Project-only 3-class softmax | `PROTOTYPE MODEL NEEDS SUPPLEMENTATION` |
| Task B2 | ASAP-supplemented 3-class softmax | `SUPPLEMENTED MODEL STILL NOT SAFE FOR INTEGRATION` |
| Task B3 | Shared-backbone dual-risk + abstention | `SAFETY-FIRST MODEL STILL NOT SAFE` |

The Task B / B2 three-class design remains
**prototype baseline — superseded for safety evaluation** (not a coding failure).
Prior `asap_*` OOF artefacts are preserved.

## Project label aggregates (unchanged)

| Class | Count | Role |
|-------|------:|------|
| printed | 221 | model fitting |
| handwritten | 55 | model fitting (Task A2 seeds) |
| non_text | 23 | model fitting |
| uncertain | 54 | challenge / abstention only |
| excluded | 2 | omitted |

- Project source groups: **6**; handwriting source groups: **3**
- Synthetic non-text (train only): **300**
- ASAP medium handwriting (train only): **350** (verified cache reused)

## Task B3 architecture

- MobileNetV3-Small + ImageNet weights; head `Linear(..., 2)`
- Outputs: `risk_logits` `[batch, 2]` → independent sigmoid
- Public outcomes via safety-first policy (ADR 0066); printed is guarded (ADR 0065)
- Threshold set version: `phase5-task-b3-dual-risk-v1`

## Loss configurations and best threshold candidates

| Config | HW→printed | HW→non_text | NT→printed | Safe-bypass | Printed retention | Slices | Gate |
|--------|----------:|------------:|-----------:|------------:|------------------:|:------:|:----:|
| dual_risk_weighted_bce | 20 | 2 | 1 | 0.60 | 0.73 | fail | fail |
| dual_risk_asymmetric_bce | 13 | 1 | 3 | 0.75 | 0.61 | fail | fail |
| dual_risk_focal | **0** | **0** | **0** | **1.00** | **0.19** | pass | fail |

Focal clears handwriting and non-text safety counts and slice gates only by
abstaining heavily (overall uncertain ≈ 0.83), so printed retention stays far
below the 80% anti-trivial floor. Weighted / asymmetric keep more printed
coverage but still leak handwriting into printed or non_text.

### Risk-head diagnostics (0.5 threshold on sigmoid; project OOF)

| Config | HW risk F1 | HW recall | NT risk F1 |
|--------|-----------:|----------:|-----------:|
| weighted_bce | 0.13 | 0.07 | 0.62 |
| asymmetric_bce | 0.44 | 0.33 | 0.47 |
| focal | 0.07 | 0.04 | 0.64 |

## Model status

- No `production_candidate` ONNX package published
- Router remains `HANDWRITING_ROUTER_ENABLED=false`
- Not wired into live OCR

## Limitations

- Dual-risk objective aligns better with asymmetric costs, but project support
  (55 HW / 23 NT / 6 groups) is still insufficient to jointly hit zero HW leaks
  and ≥80% printed retention
- ASAP short-answer domain ≠ project signatures/cursive
- Do not weaken gates; do not auto-add data or change architecture in B3

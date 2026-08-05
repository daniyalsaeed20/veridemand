# Phase 5 classifier prototype evaluation

**Status:** Task B4 route-first evaluation in progress (B/B2/B3 remain failed baselines)

**Diagnostics kind:** source-group-isolated out-of-fold prototype diagnostics  
(not final release held-out metrics)

## Baseline eras (preserved failures)

| Era | Objective | Decision |
|-----|-----------|----------|
| Task B | Project-only 3-class softmax | `PROTOTYPE MODEL NEEDS SUPPLEMENTATION` |
| Task B2 | ASAP-supplemented 3-class softmax | `SUPPLEMENTED MODEL STILL NOT SAFE FOR INTEGRATION` |
| Task B3 | Shared-backbone dual-risk + abstention | `SAFETY-FIRST MODEL STILL NOT SAFE` |
| Task B4 | Route-first vision reservation | see train-export decision token |

Three-class and dual-risk could not simultaneously achieve **zero handwriting
leakage** and **printed retention ≥ 80%**. B3 focal cleared leaks only at
~19% printed retention. Those reports, metrics, threshold searches, licensing
records, privacy evidence, and ADRs 0054–0067 are retained as valid failed
baselines.

## Project label aggregates (Task B4)

| Class | Count | Role |
|-------|------:|------|
| printed | 221 | fitting (`vision_required=0`) |
| handwritten | 55 | fitting (`vision_required=1`, HW=1) |
| uncertain | 54 | fitting (`vision_required=1`, HW loss masked) |
| non_text | 23 | fitting (`vision_required=1`, HW=0) |
| excluded | 2 | omitted |

- Project source groups: **6**; handwriting source groups: **3**
- Synthetic non-text (train only): **300**
- ASAP medium handwriting (train only): **350**

## Task B4 architecture

- MobileNetV3-Small + ImageNet weights; head `Linear(..., 2)`
- Outputs: `route_logits` `[batch, 2]` → independent sigmoid
  (`vision_required`, `handwriting_present`)
- Public policy: printed only if `p_route <= local_ocr_safe`; handwritten only
  if route and HW thresholds met; else uncertain. Model never emits `non_text`.
- Threshold set version: `phase5-task-b4-route-first-v1`
- ADRs: 0068–0071

### Distinction from B3

B3 trained `handwriting_risk` + `non_text_risk`. B4 trains **must avoid Paddle**
+ **contains handwriting**. The 54 uncertain examples supervise the primary
route head instead of remaining challenge-only.

## Task B3 dual-risk reference (failed baseline)

| Config | HW→printed | HW→non_text | NT→printed | Safe-bypass | Printed retention | Gate |
|--------|----------:|------------:|-----------:|------------:|------------------:|:----:|
| dual_risk_weighted_bce | 20 | 2 | 1 | 0.60 | 0.73 | fail |
| dual_risk_asymmetric_bce | 13 | 1 | 3 | 0.75 | 0.61 | fail |
| dual_risk_focal | **0** | **0** | **0** | **1.00** | **0.19** | fail |

## Task B4 OOF results (project-only)

Decision: **`ROUTE-FIRST MODEL STILL NOT SAFE`**

| Config | HW→printed | Unc→printed | NT→printed | HW bypass | Unc bypass | Printed retention | Gate |
|--------|----------:|------------:|-----------:|----------:|-----------:|------------------:|:----:|
| route_first_weighted_bce | 1 | 2 | 0 | 0.98 | 0.96 | 0.35 | fail |
| route_first_asymmetric_bce | 0 | 1 | 0 | 1.00 | 0.98 | 0.21 | fail |
| route_first_focal | **0** | **0** | **0** | **1.00** | **1.00** | **0.14** | fail |

Failing slice/leak keys across configs: `handwritten_to_printed`,
`uncertain_to_printed`, `signature_to_printed`, `printed_retention`.

Focal clears handwritten and uncertain → printed only by heavy abstention
(overall uncertain ≈ 0.86), so printed retention stays far below 80%.
Asymmetric nearly clears HW leak but still leaks one uncertain→printed and
retains only ~21% printed. Weighted retains more printed (~35%) but still
leaks.

Three-class and dual-risk remain insufficient for the same joint objective;
route-first aligns the primary head with the business requirement but does
not yet clear the gates on this project support.

## Model status

- No `production_candidate` ONNX package published
- Router remains `HANDWRITING_ROUTER_ENABLED=false`
- Not wired into live OCR

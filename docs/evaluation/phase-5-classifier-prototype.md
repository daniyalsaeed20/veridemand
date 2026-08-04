# Phase 5 classifier prototype evaluation

**Status:** `PROTOTYPE MODEL NEEDS SUPPLEMENTATION`

**Diagnostics kind:** source-group-isolated out-of-fold prototype diagnostics  
(not final release held-out metrics)

## Project label aggregates

| Class | Count | Role |
|-------|------:|------|
| printed | 221 | model fitting |
| handwritten | 55 | model fitting (Task A2 seeds) |
| non_text | 23 | model fitting |
| uncertain | 54 | challenge / abstention only |
| excluded | 2 | omitted |

- Project source groups: **6**
- Handwriting source groups: **3**
- Synthetic non-text (training only): **300** per configuration
- Uncertain / excluded never forced into three-class fitting

## Architecture

- MobileNetV3-Small + ImageNet `MobileNet_V3_Small_Weights.DEFAULT`
- Head: 3 logits in order `printed`, `handwritten`, `non_text`
- Torch 2.6.0 / Torchvision 0.21.0 (`model-dev` only)
- Device: CPU (locked CPU wheels)

## Preprocessing

RGB → aspect-preserving letterbox 224×224 → white pad (255) → float `[0,1]` →
ImageNet mean/std → NCHW. Matches intended runtime `model-record` contract.

## Augmentation

Conservative train-only (`phase5-conservative-aug-v1`): ±~4–5° rotation, small
translate/scale, mild brightness/contrast/grayscale, light blur, mild
JPEG/downsample, pad jitter. **No flips.**

## Balancing

Compared three configurations (≤3 limit):

1. `weighted_default_aug` — class-weighted CE
2. `balanced_sampler_default_aug` — balanced sampler (unweighted CE)
3. `weighted_stronger_aug` — class-weighted CE + slightly stronger aug

## Fold design

Leave-one-source-group-out across six project groups. Fixed epoch budget
(stage1=3 head-only, stage2=5 partial unfreeze). Outer held-out unused for early
stopping / LR / aug selection. Inner group validation not feasible with five
remaining groups — documented limitation (ADR 0056).

## Aggregate OOF metrics (best candidate: balanced sampler)

Argmax confusion (rows=true, cols=pred; order printed/handwritten/non_text):

|  | printed | handwritten | non_text |
|--|--------:|------------:|---------:|
| printed | 187 | 17 | 17 |
| handwritten | 24 | 23 | 8 |
| non_text | 6 | 0 | 17 |

- Macro F1 ≈ **0.62**
- Handwriting class recall (pre-abstention) ≈ **0.42**
- Non-text→printed at best thresholds: **0** (achievable)
- Handwritten→printed: **≥9** even under aggressive printed thresholds
- Safe-bypass (handwritten∨uncertain): **~0.73–0.91** (never 100% with ≥80% printed retention)

## Selected thresholds

No threshold set satisfied the Task B prototype safety gate. Pareto-best
candidates used very high `printed_threshold` (0.95–0.999) and still leaked
handwritten→printed while collapsing printed retention below 80% when pushed
further.

Threshold set version (search space): `phase5-task-b-prototype-v1`

## Safety-gate results

| Gate | Result |
|------|--------|
| handwritten routed printed = 0 | **FAIL** |
| handwriting safe-bypass = 100% | **FAIL** |
| non_text routed printed = 0 | pass on best candidates |
| printed retention ≥ 80% | **FAIL** when leak approaches zero |

## Uncertain challenge

Not scored with a final packaged model (gate failed before final fit/export).
OOF evidence already shows high printed confidence on some handwritten crops
(top printed probs on HW include values ≥0.99), so uncertain→printed risk remains
a warning for any future supplementation.

## Package status

**No** `production_candidate` package written under
`models/handwriting_classifier/`. Directory remains README placeholder.

## Limitations

- Only 55 project handwriting regions from three source groups
- Project crops biased by Phase 4 Paddle evidence
- No independent release held-out set
- No public handwriting supplement
- Thresholds are prototype engineering thresholds only
- Live routing not integrated; Phase 5 not passed

## Recommendation

Issue a separate bounded public-data / expanded seed supplementation task.
Do not integrate this project-only model into OCR.

# Phase 5 classifier prototype evaluation

**Status:** `SUPPLEMENTED MODEL STILL NOT SAFE FOR INTEGRATION`

**Diagnostics kind:** source-group-isolated out-of-fold prototype diagnostics  
(not final release held-out metrics)

Task B project-only training failed the safety gate
(`PROTOTYPE MODEL NEEDS SUPPLEMENTATION`). Task B2 added Handwritten ASAP
(CC BY 4.0) as training-only supplementation. Project LOSGO remains the gate.
No `production_candidate` ONNX package was published.

## Project label aggregates (unchanged)

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
- Public ASAP handwriting (training only): **150** (`asap_light`) or **350** (medium)
- Uncertain / excluded never forced into three-class fitting
- ASAP samples never enter project OOF metrics

## Architecture

- MobileNetV3-Small + ImageNet `MobileNet_V3_Small_Weights.DEFAULT`
- Head: 3 logits in order `printed`, `handwritten`, `non_text`
- Torch 2.6.0 / Torchvision 0.21.0 (`model-dev` only)
- Device: CPU (locked CPU wheels)

## Public supplement (Task B2)

- Dataset: Handwritten ASAP Short Answer Scoring (Zenodo 8088866)
- Licence: CC BY 4.0 (verified via Zenodo API)
- Archive MD5: `d365ea3ca8afc19d4758a22daa2e1ea2`
- Local SHA-256: `7881cd037f442585d9f9584258fa512ac68d1d9eaf7ce059d0c18c4d6278c917`
- Access date: 2026-08-04
- Subset: `phase5-asap-subset-v1` (350 QC-passed; light=150); transform `phase5-asap-crop-v1`
- Prompt groups: 2
- Transcription labels discarded; class label is only `handwritten`
- NIST SD19 / EMNIST: **not used**

## Task B2 configurations (≤3)

1. `asap_light` — 150 ASAP + project; class-weighted CE
2. `asap_medium` — 350 ASAP + project; class-weighted CE
3. `asap_medium_project_weighted` — 350 ASAP + project HW sample multiplier 4

## Aggregate OOF metrics (best macro F1: asap_medium)

Argmax confusion (rows=true, cols=pred; order printed/handwritten/non_text):

|  | printed | handwritten | non_text |
|--|--------:|------------:|---------:|
| printed | 201 | 8 | 12 |
| handwritten | 12 | 36 | 7 |
| non_text | 6 | 0 | 17 |

- Macro F1 ≈ **0.74** (improved vs Task B ≈0.62)
- Handwriting class recall (pre-abstention) ≈ **0.66** (was ≈0.42)
- Best threshold candidates still fail aggregate and/or slice gates

### Best threshold candidates (lexicographic; none pass)

| Config | HW→printed | NT→printed | Safe-bypass | Printed retention | Slice gates |
|--------|----------:|----------:|------------:|------------------:|:-----------:|
| asap_light | 9 | 1 | 0.78 | 0.70 | fail |
| asap_medium | 2 | 2 | 0.93 | 0.61 | fail |
| asap_medium_project_weighted | 1 | 1 | 0.95 | 0.68 | fail |

Threshold set version: `phase5-task-b2-asap-v1`

## Cursive / signature slices (project seeds)

On best `asap_medium_project_weighted` candidate thresholds:

| Slice | support | printed | handwritten | uncertain | non_text |
|-------|--------:|--------:|------------:|----------:|---------:|
| digits | 10 | 0 | 6 | 4 | 0 |
| hand_printed | 10 | 1 | 6 | 3 | 0 |
| cursive | 22 | 0 | 12 | 10 | 0 |
| signature | 11 | 0 | 6 | 3 | 2 |
| longer_note | 2 | 0 | 1 | 1 | 0 |

Required: cursive/signature → printed = 0 **and** → non_text = 0.  
Signatures still route to **non_text** (2) under the best candidate → slice gate fail.
Cursive improves vs Task B but aggregate HW→printed and printed retention cannot
be satisfied together at 100% safe-bypass with ≥80% printed retention.

## Recommendation (smallest next technical adjustment)

Do **not** weaken gates. Prefer: (1) targeted project signature / cursive seed
expansion or acquisition-matched synthetics for those slices, then (2) modest
loss/sampler emphasis on signature crops — before architecture changes or
another public corpus.

## Package

- **No** `production_candidate` under `models/handwriting_classifier/`
- Router remains disabled; OCR not integrated

## Attribution

Gold, Christian; Zesch, Torsten (2020). Handwritten ASAP Short Answer Scoring
(Version 1.0) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.8088866
Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).

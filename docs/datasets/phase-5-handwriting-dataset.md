# Phase 5 handwriting crop dataset

## Purpose

Private region-crop dataset for Phase 5 handwriting **style** classification
labels. This is tooling only in Task 3A — no training, no OCR wiring, no ONNX
export.

## Doctrine

- Extract geometry from the least expensive reliable source (Phase 4 artefacts
  or validated manual regions). Never invent coordinates.
- **Human labels only.** OCR text, confidence, heuristics, and filenames are
  never ground truth.
- Manifests contain **no text fields**.
- Private crops/pages/manifests stay under `fixtures/private/phase5/` and are
  gitignored (except `README.example.md`).

## Layout

See `fixtures/private/phase5/README.example.md`. Initialize with:

```bash
pnpm phase5:crops:init
```

## Candidate sources

| Source key | Meaning |
|------------|---------|
| `visual_detection` | Phase 4 visual blocks |
| `full_page_ocr` | Phase 4 lines/words geometry |
| `targeted_repair` | Repair region geometry when present |
| `heuristic_region` | Local heuristic proposals |
| `noise_region` | Noise / clutter negatives |
| `manual_region` | Human-drawn / JSONL import |
| `synthetic_negative` | Synthetic non-text / hard negative |

Padding policy: `phase5-crop-pad-v1` (8% of max side, clamp to page, recorded).

## Commands

| Script | Role |
|--------|------|
| `pnpm phase5:crops:export -- --page-result … --page-image …` | Export from Phase 4 JSON |
| `pnpm phase5:crops:import-manual -- --regions … --page-image …` | Manual JSONL import |
| `pnpm phase5:crops:verify` | Hash/geometry consistency |
| `pnpm phase5:labels:serve` | Loopback blind labeler |
| `pnpm phase5:labels:resolve` | Derive resolved labels |
| `pnpm phase5:dataset:split -- --seed 42` | Group-aware split |
| `pnpm phase5:dataset:freeze-heldout -- --crop-ids …` | Explicit held-out freeze |
| `pnpm phase5:dataset:report` | Private + aggregate readiness |

## Future public-dataset import (contract only)

A future importer may accept a **public** JSONL of geometry + licence metadata
with the same `CropRecord` schema and opaque IDs. Task 3A does **not** download
or vendor any public corpora. Any public import must:

1. Refuse private/case paths.
2. Preserve licence / attribution sidecar outside gitignored private trees.
3. Never treat public OCR transcripts as VeriDemand labels.

## Readiness

Committed aggregate: [`docs/evaluation/phase-5-dataset-readiness.md`](../evaluation/phase-5-dataset-readiness.md).

Status target after Task 3A tooling: **DATASET TOOLING READY — HUMAN LABELLING REQUIRED**.

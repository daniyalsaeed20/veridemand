# Phase 5 handwriting crop dataset

## Purpose

Private region-crop dataset for Phase 5 handwriting **style** classification
labels. Tasks 3A–3B delivered tooling and private corpus population. Task 3C
adds coverage audit and a 600-crop blinded annotation pilot before full review.
No training, no ONNX export, no live OCR wiring.

## Doctrine

- Extract geometry from the least expensive reliable source (Phase 4 artefacts
  or validated manual regions). Never invent coordinates.
- **Human labels only.** OCR text, confidence, heuristics, filenames, and
  candidate provenance are never ground truth.
- Manifests contain **no text fields**.
- Private crops/pages/manifests/overlays/pilot queues stay under
  `fixtures/private/phase5/` and are gitignored (except `README.example.md`).

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

Private populate currently yields **lines → `full_page_ocr`** only. Blocks are
1:1 line proxies and are skipped by `export-all` to avoid duplicates. Repair
regions are empty in the current private evidence. See the provenance audit.

## Commands

| Script | Role |
|--------|------|
| `pnpm phase5:crops:register` | Register PDFs from local batch manifest |
| `pnpm phase5:crops:populate-evidence` | Offline render + geometry (OCR group) |
| `pnpm phase5:crops:export-all` | Export all populated private pages |
| `pnpm phase5:crops:verify` | Hash/geometry consistency |
| `pnpm phase5:dataset:dedupe-sources` | Dedupe source-manifest by page_id |
| `pnpm phase5:dataset:provenance` | Candidate-source provenance audit |
| `pnpm phase5:dataset:block-coverage` | Skipped-block vs line coverage |
| `pnpm phase5:coverage:build` | Page overlays + coverage queue |
| `pnpm phase5:coverage:serve` | Loopback coverage reviewer |
| `pnpm phase5:labels:pilot` | Build 600-crop dual pilot queues |
| `pnpm phase5:labels:serve -- --queue pilot-primary --reviewer rev_<id>` | Default human task |
| `pnpm phase5:labels:serve -- --queue pilot-secondary --reviewer rev_<other>` | Blind secondary |
| `pnpm phase5:labels:queue` | Rebuild full primary queue (not default) |
| `pnpm phase5:dataset:report` | Private + aggregate readiness |

## Readiness

Committed aggregate: [`docs/evaluation/phase-5-dataset-readiness.md`](../evaluation/phase-5-dataset-readiness.md).

Status after Task 3C: **PRIVATE CORPUS POPULATED — COVERAGE AND ANNOTATION PILOT REQUIRED**.

Pilot: [`docs/evaluation/phase-5-annotation-pilot.md`](../evaluation/phase-5-annotation-pilot.md).

Source-group adequacy: [`docs/evaluation/phase-5-source-group-adequacy.md`](../evaluation/phase-5-source-group-adequacy.md).

No classifier training is authorised until human labels and an adequacy decision exist.

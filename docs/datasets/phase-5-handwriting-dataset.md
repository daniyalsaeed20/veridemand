# Phase 5 handwriting crop dataset

## Purpose

Private region-crop dataset for Phase 5 handwriting **style** classification
labels used later for routing (printed→Paddle; handwritten/uncertain→
`reserved_for_vision` / `pending_phase_6`; non_text→suppress). Tasks 3A–3D
delivered tooling, corpus, dual pilot queues, and coverage audit. Task A adds a
~300-crop single-pass prototype queue (ADR 0053). Dual review and full coverage
correction remain parked release-hardening tools. No training, no ONNX export,
no live OCR wiring, no vision-provider calls in this dataset work.

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
| `pnpm phase5:labels:prototype-queue` | Build ~300-crop prototype queue from pilot |
| `pnpm phase5:labels:serve -- --queue prototype-primary --reviewer proto_reviewer_01` | Default Task A human path |
| `pnpm phase5:labels:prototype-report` | Aggregate prototype label report |
| `pnpm phase5:handwriting-seeds:queue` | Build targeted handwriting-seed page queue (Task A2) |
| `pnpm phase5:handwriting-seeds:serve -- --reviewer handwriting_reviewer_01` | Loopback handwriting seed collector |
| `pnpm phase5:handwriting-seeds:verify` | Verify seed events / crop hashes / geometry |
| `pnpm phase5:handwriting-seeds:resolve` | Exact-dedupe seeds; perceptual warnings |
| `pnpm phase5:handwriting-seeds:report` | Aggregate handwriting seed readiness |
| `pnpm phase5:labels:pilot` | Build 600-crop dual pilot queues (parked) |
| `pnpm phase5:labels:serve -- --queue pilot-primary --reviewer rev_<id>` | Dual-pilot primary (parked) |
| `pnpm phase5:labels:serve -- --queue pilot-secondary --reviewer rev_<other>` | Blind secondary (parked) |
| `pnpm phase5:labels:queue` | Rebuild full primary queue (parked) |
| `pnpm phase5:dataset:report` | Private + aggregate readiness |

## Readiness

Committed aggregate: [`docs/evaluation/phase-5-dataset-readiness.md`](../evaluation/phase-5-dataset-readiness.md).

Status: **PRIVATE CORPUS POPULATED — PROTOTYPE LABELLING PATH OPEN** (ADR 0053).

Prototype labels: [`docs/evaluation/phase-5-prototype-labels.md`](../evaluation/phase-5-prototype-labels.md)
(after human review).

Pilot (parked dual-review): [`docs/evaluation/phase-5-annotation-pilot.md`](../evaluation/phase-5-annotation-pilot.md).

Source-group adequacy: [`docs/evaluation/phase-5-source-group-adequacy.md`](../evaluation/phase-5-source-group-adequacy.md)
— insufficient for **release** held-out freeze; does not block prototype training.

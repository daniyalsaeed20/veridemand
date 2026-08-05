# Phase 5 — Detector recall calibration (Task C1)

## Purpose

Before classifier retraining, determine whether the existing Paddle detector,
a calibrated variant, the same-family PP-OCRv5 server detector, or a dual-
detector merge can locate **all** known project handwriting seeds.

Detection coverage only. No classifier training. No live routing. No Phase 6.

## Runtime doctrine (unchanged)

```text
page → text detection → detected regions → (future) writing-style classifier
```

The classifier can act only on regions the detector supplies.

## Isolation

| Flag / path | Value |
|-------------|-------|
| `PHASE5_DETECT_FIRST_SHADOW_ENABLED` | `false` |
| `HANDWRITING_ROUTER_ENABLED` | `false` |
| Live OCR | Phase 4 combined `PaddleOCR.predict` |
| Server detector | Offline bootstrap + shadow only |
| Dual merge | Offline calibration only |

## Geometry matching (seed coverage)

Primary gate uses Task C0 `classify_seed_coverage`:

| Kind | Criteria |
|------|----------|
| exact / near_exact | IoU ≥ 0.90 (exact if ≥ 0.98) |
| contained | containment ≥ 0.50 and detector area ≥ 1.05× seed |
| fragmented | ≥1 box with IoU ≥ 0.25 (or ≥2 such boxes) |
| missed | otherwise |

Sensitivity aggregates (reporting only):

- **strict** — exact / near_exact
- **containment-friendly** — exact / near_exact / contained
- **fragment-union** — above + fragmented

Gate selection uses the C0 “detected = not missed” definition (includes fragments).

## Predict-time parameters

PaddleX `TextDet` predict kwargs (unprefixed):

```text
thresh, box_thresh, unclip_ratio, limit_side_len, limit_type
```

Task C0 called `detect_text` with **no** kwargs (model YAML intrinsic defaults:
PostProcess thresh 0.3 / box_thresh 0.6 / unclip 1.5, resize_long 960).

Settings defaults (Phase 4 combined path) use `limit_side_len=1600` among other
knobs; applying those explicitly is a calibrated variant, not the C0 intrinsic
baseline.

## Bounded grid

At most **12** materially different configs (`phase5-detector-calibration-v1`).
No unbounded search. Pathological near-full-page boxes are rejected.

Includes:

- mobile C0 intrinsic
- mobile Settings defaults
- mobile soft / recall / faint variants
- server intrinsic / defaults / calibrated
- dual merge (`phase5-dual-detector-merge-v1`)

## Merge algorithm

`phase5-dual-detector-merge-v1`:

- exact / high-IoU equivalents → one region with combined provenance
- neighbouring non-overlapping lines stay separate
- partial overlaps retained as fragments for analysis
- stable `dfmrg_*` IDs; deterministic ordering

## Known-seed zero-miss gate

Eligible only when, on the 55 confirmed seeds:

- overall misses = 0
- digits / hand-print / cursive / signature / longer-note misses = 0
- no pathological full-page boxes
- recognition compatibility ≠ `not_acceptable`
- corpus run completes without OOM

If multiple pass: fewest regions → lowest detector time → least recognition
degradation → simplest deployment → prefer mobile-only over dual.

## Commands

```text
pnpm models:ocr:bootstrap:server-det
pnpm phase5:detector-calib:baseline
pnpm phase5:detector-calib:grid
pnpm phase5:detector-calib:corpus
pnpm phase5:detector-calib:recognise-sample
pnpm phase5:detector-calib:select
pnpm phase5:detector-calib:build-v2   # only if candidate ready
```

Private aggregates under
`fixtures/private/phase5/reports/detector-calibration/` (gitignored).

## Outcomes

- `HANDWRITING-CAPABLE DETECTOR CANDIDATE READY` → record candidate; build
  `phase5-detector-first-regions-v2` without overwriting v1; do **not** make it
  live; do **not** retrain the classifier in Task C1.
- `DETECTOR COVERAGE STILL INSUFFICIENT` → report Pareto candidates and miss
  slices; do not weaken the gate; do not retrain.

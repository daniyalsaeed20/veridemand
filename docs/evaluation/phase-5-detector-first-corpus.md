# Phase 5 — Detector-first private corpus

## Why

The existing private crop corpus was built from **combined** Paddle
detect+recognise results. Regions with empty recognition were dropped, and
handwriting the combined pipeline never boxed may be absent. Task C0 builds a
**separate** detector-first pool so a future router trains on the same crop
contract it will see at runtime.

This is an **input-pipeline correction**, not another model redesign. No
classifier is trained in Task C0.

## Corpus version

```text
phase5-detector-first-regions-v1
```

Separate from the post-recognition crop corpus under `crops/`.

## Build

```text
pnpm phase5:detector-corpus:build
pnpm phase5:detector-corpus:compare
```

Requires the OCR environment (`uv run --group ocr`), not `model-dev`.
On Windows, do not sync `model-dev` and `ocr` into the same venv.

## Aggregate results (local private batch)

| Metric | Value |
|--------|------:|
| Source groups | 6 |
| Documents | 6 |
| Pages | 215 |
| Detector-first regions | 17,581 |
| Canonical after exact dedupe | 11,037 |
| Exact duplicates | 6,544 |
| Recognised | 4,205 |
| Empty recognition | 2,478 |
| Low-confidence recognition | 3,948 |
| Rejected recognition | 406 |
| Failed recognition | 0 |
| Label transfers | 0 (all left unlabelled; framing differs from post-rec crops) |
| Recognition equivalence | acceptable_for_next_integration_task |

Timing (full build, detect-first only): detect ≈ 202s; recognise ≈ 2695s.

## Legacy comparison (10-page sample)

| Metric | Value |
|--------|------:|
| Detector-first regions | 501 |
| Legacy combined regions | 499 |
| Matched (IoU ≥ 0.50) | 466 |
| Detector-first only | 35 |
| Legacy only | 33 |
| Recognition equivalence | acceptable_for_next_integration_task |

Sample timing: detect ≈ 9.5s; recognise ≈ 80s; legacy predict ≈ 182s.

## Recognition status (metadata only)

```text
not_run | recognised | empty | low_confidence | failed | rejected
```

Recognition status never drops a detector region. Empty/failed/low-confidence
regions are retained in the private manifest.

## Label transfer

Existing human labels transfer only via exact crop SHA-256 or strict geometry
identity (ADR 0075). On this first detector-first build, **no** labels
transferred — crop framing differs from the post-recognition corpus. Fresh
labelling is required before router retraining.

## Privacy

Committed evaluation docs use aggregates only. Private manifests omit OCR text.
No montages, no OpenAI, no Phase 6 provider calls.

## Task C1 note

Task C1 calibrated detectors offline but did **not** promote
`phase5-detector-first-regions-v2` because the known-seed zero-miss gate failed
(`DETECTOR COVERAGE STILL INSUFFICIENT`). This v1 corpus remains the preserved
Task C0 baseline. See `docs/evaluation/phase-5-detector-candidate-comparison.md`.

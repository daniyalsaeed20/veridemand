# Phase 5 — Detector candidate comparison (Task C1)

## Decision

```text
DETECTOR COVERAGE STILL INSUFFICIENT
```

No configuration reached the known-seed zero-miss prototype gate on the
current 55 handwriting seeds. Classifier retraining remains blocked.

## Baseline (Task C0 reproduction)

| Metric | Value |
|--------|------:|
| Model | `PP-OCRv5_mobile_det` (intrinsic / no predict kwargs) |
| Seeds | 55 |
| Detected | 36 |
| Missed | 19 |
| Overall recall | 0.655 |
| Digits | 0.50 |
| Hand-print | 1.00 |
| Cursive | 0.545 |
| Signatures | 0.636 |
| Longer notes | 1.00 |
| Fragments | 6 |

Matches Task C0 published aggregates.

## Candidates evaluated

Materially different configs ≤ 12 plus one extra merged pair after expensive
server variants were skipped for runtime budget.

| Label | Family | Overall | Misses | Digits | Hand-print | Cursive | Signatures | Longer | Regions | Time (s) |
|-------|--------|--------:|-------:|-------:|-----------:|--------:|-----------:|-------:|--------:|---------:|
| mobile_c0_intrinsic | mobile | 0.655 | 19 | 0.50 | 1.00 | 0.545 | 0.636 | 1.00 | 488 | 8.4 |
| mobile_settings_defaults | mobile | 0.800 | 11 | 0.90 | 0.90 | 0.864 | 0.455 | 1.00 | 540 | 21.8 |
| mobile_soft_thresh | mobile | 0.836 | 9 | 0.90 | 0.90 | 0.955 | 0.455 | 1.00 | 549 | 21.8 |
| mobile_recall_bias | mobile | 0.855 | 8 | 1.00 | 0.90 | 1.000 | 0.455 | 1.00 | 565 | 22.3 |
| mobile_unclip_1920 | mobile | 0.691 | 17 | 0.70 | 0.80 | 0.636 | 0.455 | 1.00 | 561 | 32.4 |
| mobile_faint_2400 | mobile | 0.855 | 8 | 1.00 | 0.90 | 1.000 | 0.455 | 1.00 | 586 | 44.7 |
| server_intrinsic | server | 0.764 | 13 | 0.80 | 1.00 | 0.727 | 0.545 | 1.00 | 477 | 154.2 |
| server_settings_defaults | server | 0.855 | 8 | 1.00 | 0.90 | 1.000 | 0.364 | 1.00 | 512 | 416.3 |
| merged_intrinsics | merged | 0.800 | 11 | 0.80 | 1.00 | 0.727 | 0.727 | 1.00 | 597 | 159.0 |
| merged_mobile_recall_bias_plus_server_defaults | merged | 0.873 | 7 | 1.00 | 0.90 | 1.000 | 0.455 | 1.00 | 645 | 428.4 |

Skipped (runtime budget after server_settings_defaults ≈ 416 s on seed pages):

- `server_recall_1920`
- `server_faint_2400`
- `merged_faint_2400`

Server model provenance (shadow only):

| Field | Value |
|-------|-------|
| Name | `PP-OCRv5_server_det` |
| Source | PaddleX/BOS official cache |
| Bootstrap | `pnpm models:ocr:bootstrap:server-det` |
| Tree hash | `275d3f1981d71e1383a900b2948c6a8f1c0c4f94e32031e424bff065558fadf7` |
| Size | 88 358 342 bytes |
| Live detector replaced | **false** |

## Pareto front (incomplete coverage)

Best overall recall: **merged_mobile_recall_bias_plus_server_defaults**
(7 misses, recall 0.873). Closest single-detector ties at 8 misses:
`mobile_recall_bias`, `mobile_faint_2400`, `server_settings_defaults`.

When quality is otherwise similar, mobile-only remains preferable to dual
merge for deployment simplicity — but **none** satisfy the zero-miss gate.

## Remaining miss slices (best incomplete candidate)

Aggregates only (no private page IDs):

| Slice | Missed |
|-------|-------:|
| Overall | 7 |
| Signatures | 6 |
| Hand-print | 1 |
| Digits | 0 |
| Cursive | 0 |
| Longer notes | 0 |

Signature coverage is the dominant residual failure mode across calibrated
and merged candidates. Soft-threshold mobile configs raise cursive/digit
recall but do not recover the missed signatures (often worsen signature
recall versus the C0 intrinsic baseline).

Recognition compatibility for shortlisted candidates remains
`not_evaluated` for selection purposes: the known-seed gate failed first, and
the bounded recognition sample was stopped after gate failure to avoid
unnecessary private corpus churn. No candidate is promoted.

## Isolation / privacy

- Live flags remain off; worker does not load server det or merge.
- No private IDs, OCR text, crops, or model binaries committed.
- Task C0 corpus `phase5-detector-first-regions-v1` preserved (no v2 build).

## Next decisions (not implemented)

- Fine-tune a handwriting-sensitive detector, **or**
- Add a page-level vision-reservation fallback for undetected handwriting.

Do not weaken the known-seed gate.

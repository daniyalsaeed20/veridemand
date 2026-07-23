# Phase 4.3 — Adaptive image OCR performance + multipage progress

## Phase 4.3 Final Acceptance Result

**PASSED** on Windows development runtime after progress/lifecycle corrections
on `fix/phase-4-adaptive-image-ocr-performance`.

## Starting Tag and Commit

- Starting tag: `phase-4-visual-detection-printed-ocr-v1.3` (`c1b5bae`)
- Branch: `fix/phase-4-adaptive-image-ocr-performance`

## Model Bootstrap Status

`pnpm models:ocr:bootstrap`, `pnpm models:ocr:verify`, and
`pnpm verify:visual-runtime` succeeded with
`PP-OCRv5_mobile_det` / `PP-OCRv5_mobile_rec`.

## Worker and Readiness Status

OCR worker generation 1 ready; `/health/ready` returns JSON `status: ready`
(HTTP 200). No mid-run model download.

## Private Document Runtime

Opaque label: **private-two-page-A** (gitignored local PDF; not committed).
Page count: 2. Final status: `visual_processing_complete`. Progress cap: 65%.
Visual result available: true. Worker generation: 1. No worker restart. No page
timeout. No Future warning observed.

## Page 1 Timing

Paddle pipeline held overall near 43.8% during inference (~75s wall to
pipeline complete). Page 1 published at overall **52.0%** with
`pages_completed=1` (not 65%).

## Page 2 Timing

Page 2 started at overall **52.5%** (no overall/phase regression). Document
elapsed ~102s at terminal. Same worker generation 1.

## OCR Result Availability

Visual page results available; aggregate confidence and line/word counts only
recorded in runtime (no OCR strings in progress events or this report).
Handwriting remains `pending_phase_5`. Source label remains provisional
printed visual OCR.

## Multipage Progress Correction

Document-wide `page_fraction` maps into overall **41–63**; summary/reconcile
advances **63–65**. Never `pages_completed=N` with `page_percent=100` toward
the fraction. Major phase derives monotonically from overall:
`(overall - 35) / 30 * 100`.

## Operation Lifecycle Correction

Combined `PaddleOCR.predict` uses public operation **`paddle_ocr_pipeline`**
(ADR 0024). Coordinator owns public start/terminal pairs. Selection completes
once. Summary publication and authority reconciliation emit before terminal
`visual_processing_complete`.

## Terminal Document Publication

Session document reaches terminal Phase 4 status at 65% with visual fields
populated. SSE emits `document.visual_processing_completed`.

## Frontend Progress Correction

`viewerApi` ProgressEvent enum includes visual SSE types so session refetch
runs during OCR. Client monotonic floors prevent stale native % overwriting
visual progress. DocumentCard shows three-level meters and terminal copy.

## Second-Document Worker Reuse

Synthetic follow-up processed on the same server without restart. Only one
`ocr_worker_process_started` (generation 1) for the process lifetime.

## Privacy Verification

Private PDF remains under gitignored `tmp/` / `fixtures/private/`. Not staged.
Opaque label only in this report. No OCR text in progress logs.

## Tests

- `backend/tests/test_phase43_multipage_progress.py`
- `backend/tests/test_phase43_progress_lifecycle.py`
- Real Paddle: `backend/tests/test_ocr_integration.py`
- Frontend: monotonic progress + visual SSE invalidate

## Exact Detection Bottleneck (prior)

Paddle printed-text detection on an unnecessarily upscaled full-page scan
bitmap (~4733 x 6083 at 200 DPI from a ~1704 x 2190 source), timing out at
180s x 2 attempts (`ocr_page_timeout`).

## Adaptive Render Policy

Implemented in `page_raster_policy.py` + `renderer.py`. Defaults: mobile
PP-OCRv5, `ocr_text_det_limit_side_len=1600`, source-resolution-aware render.

## Manual Readiness Check

`Invoke-RestMethod` is a PowerShell cmdlet (not a repo file). See
[`docs/smoke/README.md`](../smoke/README.md).

## Phase Boundary Confirmation

No Phase 5 (handwriting / ONNX / OpenAI / PP-Structure). Progress cap remains
65%. Timeouts were not raised to pass acceptance.

## Corrective Tag

`phase-4-visual-detection-printed-ocr-v1.4` → `611250eae88a8a1fc9c457b97dc8e9a37c905e52`
(after CI on exact final SHA). Does not move v1 / v1.1 / v1.2 / v1.3.

## CI

https://github.com/daniyalsaeed20/veridemand/actions/runs/30042122825

PHASE 4.3 PRIVATE ACCEPTANCE PASSED — READY FOR PHASE 5

# Phase 4.3 — Adaptive image OCR performance

## Phase 4.3 Result

Corrective hardening after `phase-4-visual-detection-printed-ocr-v1.2`: stop
200-DPI upscaling of full-page scans, restore mobile PP-OCRv5 as the CPU
baseline, bound detector input size, fix Future exception retrieval, and stop
the frontend sticking near native 32% after visual failure.

## Exact Detection Bottleneck

Paddle printed-text detection on an unnecessarily upscaled full-page scan
bitmap (~4733 x 6083 at 200 DPI from a ~1704 x 2190 source), timing out at
180s x 2 attempts (`ocr_page_timeout`).

## Source and Render Dimensions

| Field | Value |
|-------|--------|
| Canonical (private-class) | ~1704 x 2190 pt |
| Embedded source | ~1704 x 2190 px |
| Naive 200 DPI render | ~4733 x 6083 px (confirmed by unit arithmetic) |
| Adaptive policy | `pdfium_render_capped_to_source_resolution` (default path) |
| Effective DPI (identity scan) | ~72 (no upscale) |

Synthetic identity fixture: `fixtures/synthetic/ocr/full-page-scan-identity.pdf`.

## Adaptive Render Policy

Implemented in [`page_raster_policy.py`](../backend/app/extraction/visual/page_raster_policy.py)
+ [`renderer.py`](../backend/app/extraction/visual/renderer.py). Records
`requested_dpi`, `effective_dpi`, `downscale_reason`,
`source_resolution_cap_applied`, `render_source_policy`.

## Model Benchmark

Default CPU baseline restored to **PP-OCRv5_mobile_det / PP-OCRv5_mobile_rec**
(ADR 0023). Medium v6 remains settings-selectable for comparison.
Harness: `scripts/benchmark_phase43_ocr.py`.

## Detector Input Benchmark

Default `ocr_text_det_limit_side_len` **1600** (bounded midpoint; see
`docs/phases/phase-4.3-detector-benchmark.json`). Previous 2400 retained as
comparison risk class for oversized pages.

## Dense-Form Findings

Synthetic dense ruled / grid fixtures added. Ruling-line suppress fallback is
**not enabled** — no measured evidence yet that DB/postprocess false regions
dominate over oversized input size. Revisit only with timed preprocess vs
infer vs postprocess splits.

## CPU/GPU Decision

CPU remains the supported Windows baseline. GTX 1060 (3 GB) is not
auto-enabled (below current Paddle Windows GPU compute-capability /
VRAM expectations). Documented in ADR 0023.

## Timeout Behaviour

Page timeout still terminates the attempt, cleans incomplete outputs, and
retries at most once. On the **final** attempt, the manager does **not**
restart an unused third worker before finalising the failed request.

## Future Cleanup

`ActiveRequest` Futures call `.exception()` / `.result()` after
`set_exception` / `set_result` so asyncio no longer warns
“Future exception was never retrieved.” Regression in
`test_phase43_adaptive_render.py`.

## Frontend Progress Correction

`_document_progress_percent` floors visual statuses above native bands and
forces **65%** on `visual_processing_failed`. DocumentCard shows the specified
timeout failure copy (operation, page, attempts, error, canonical available).

## Real Two-Page Verification

Private regression PDF was **not** present under `fixtures/private/` in this
workspace. Synthetic identity-scan + unit arithmetic confirm the 200 DPI
upscale class. Operators should re-run `pnpm dev:backend` on the gitignored
corpus and attach opaque metrics before claiming production pass on that file.

## Tests

- Backend: `backend/tests/test_phase43_adaptive_render.py` (policy, DPI cap,
  progress, Future cleanup)
- Frontend: DocumentCard terminal failure details
- Fixtures: full-page-scan-identity, dense-ruled-form, large-grid-page

## Commits

Branch `fix/phase-4-adaptive-image-ocr-performance` from `phase-4-visual-detection-printed-ocr-v1.2` (`606f041`).

## Corrective Tag

`phase-4-visual-detection-printed-ocr-v1.3` (after CI on exact final SHA).
Does not move v1 / v1.1 / v1.2.

## CI

https://github.com/daniyalsaeed20/veridemand/actions/runs/30017694569  
Final SHA: `b7c601d5f69a712edb44e5ea00410a3203fe6988` (pre-report polish may add a docs commit; tag peels to the CI-green delivery SHA after report update).

## Phase Boundary Confirmation

No Phase 5 (handwriting / ONNX / OpenAI / PP-Structure). Native trust
thresholds unchanged. Progress cap remains 65%. Timeout seconds were not
raised as the primary fix.

PHASE 4.3 FIX INCOMPLETE — DO NOT START PHASE 5

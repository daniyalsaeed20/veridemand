# ADR 0023 — Adaptive OCR render + mobile PP-OCRv5 CPU baseline

## Status

Accepted (Phase 4.3)

## Context

Phase 4 / 4.1 / 4.2 calibrated on **PP-OCRv6 medium** at unconditional **200 DPI**
([ADR 0018](0018-paddleocr-local-inference.md), [ADR 0017](0017-pypdfium2-page-rendering.md)).
Real full-page scans whose MediaBox points equal source pixels were upscaled to
~4733×6083, then timed out in Paddle text detection (180s × 2). The Source of
Truth still names **mobile PP-OCRv5** for the initial CPU target; that choice was
not rewritten in the SoT.

A development GTX 1060 (3 GB) is below current PaddlePaddle Windows GPU
compute-capability requirements and must not become a production dependency.

## Decision

1. **Adaptive render-source policy** before OCR:
   - `embedded_full_page_image` when a single near-full-page raster is present;
   - `pdfium_render_capped_to_source_resolution` when the page is a scan but the
     embed path is unavailable;
   - `pdfium_render` for vector/native pages that still need visual OCR.
   Never upscale a full-page scan above its source resolution. Record
   `requested_dpi`, `effective_dpi`, `downscale_reason`, and
   `source_resolution_cap_applied`.

2. **Default models:** `PP-OCRv5_mobile_det` / `PP-OCRv5_mobile_rec` on CPU.
   Medium v6 remains available via settings for comparison benchmarks. Models
   are never downloaded during document processing.

3. **Default `ocr_text_det_limit_side_len`:** **1600** (bounded from the Phase 4.3
   detector-side matrix; not chosen solely to pass one private PDF).

4. **CPU remains the supported Windows baseline.** GPU is not auto-enabled.
   A later supported GPU path would require a separate architecture decision
   (driver/CUDA stack meeting Paddle’s published minimum compute capability,
   VRAM budget above model + activation peaks, and security review). Do not
   downgrade Paddle merely to force a GTX 1060 into service.

5. Do **not** raise `OCR_PAGE_TIMEOUT_SECONDS` as the primary fix for oversized
   renders. Timeouts still terminate, clean `.part` files, resolve Futures, and
   retry at most once.

## Consequences

- Operators must bootstrap mobile models (`pnpm models:ocr:bootstrap`).
- CI model cache keys change with the default model names.
- ADR 0018’s medium-model default is superseded for the CPU baseline; 0018’s
  local-only / no-cloud / 65% progress decisions remain.
- Dense-form ruling-line suppression stays **off** until measured evidence shows
  postprocessing domination by grid false positives.

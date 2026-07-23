"""One-page canonical PDF rendering via pypdfium2."""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from backend.app.contracts.errors import ErrorCode
from backend.app.extraction.visual.errors import VisualOcrError
from backend.app.extraction.visual.models import RenderedPage
from PIL import Image

logger = logging.getLogger("veridemand.visual.renderer")

_POINTS_PER_INCH = 72.0


@dataclass(frozen=True, slots=True)
class RenderLimits:
    """DPI and pixel caps for a single page render."""

    target_dpi: float
    min_effective_dpi: float
    max_render_pixels: int
    max_render_side_pixels: int
    dimension_tolerance_points: float


def compute_effective_dpi(
    *,
    page_width_points: float,
    page_height_points: float,
    target_dpi: float,
    min_effective_dpi: float,
    max_render_pixels: int,
    max_render_side_pixels: int,
) -> float:
    """Return a uniform DPI that respects pixel caps, floored at min DPI."""

    if page_width_points <= 0 or page_height_points <= 0:
        raise VisualOcrError(
            ErrorCode.VISUAL_RENDER_FAILED,
            "Canonical page dimensions are invalid.",
            operation="compute_effective_dpi",
            failing_component="renderer",
        )

    dpi = float(target_dpi)
    while dpi + 1e-9 >= min_effective_dpi:
        width_px = page_width_points * dpi / _POINTS_PER_INCH
        height_px = page_height_points * dpi / _POINTS_PER_INCH
        pixels = width_px * height_px
        if (
            pixels <= max_render_pixels
            and width_px <= max_render_side_pixels
            and height_px <= max_render_side_pixels
        ):
            return dpi
        # Uniform shrink toward the limiting factor.
        side_factor = min(
            max_render_side_pixels / max(width_px, 1.0),
            max_render_side_pixels / max(height_px, 1.0),
            (max_render_pixels / max(pixels, 1.0)) ** 0.5,
        )
        next_dpi = dpi * min(side_factor, 0.95)
        if next_dpi >= dpi:
            next_dpi = dpi * 0.9
        dpi = next_dpi

    raise VisualOcrError(
        ErrorCode.VISUAL_PAGE_RESOURCE_LIMIT,
        "Page exceeds render resource limits at minimum DPI.",
        operation="compute_effective_dpi",
        failing_component="renderer",
    )


def _expected_pixel_size(
    page_width_points: float, page_height_points: float, dpi: float
) -> tuple[int, int]:
    width = max(1, round(page_width_points * dpi / _POINTS_PER_INCH))
    height = max(1, round(page_height_points * dpi / _POINTS_PER_INCH))
    return width, height


def render_page(
    pdf_path: Path,
    *,
    page_number: int,
    page_width_points: float,
    page_height_points: float,
    limits: RenderLimits,
    pdf_document: pdfium.PdfDocument | None = None,
    plan: Any | None = None,
) -> RenderedPage:
    """Render one 1-based page to an owned PIL RGB image.

    The caller owns the returned image. When ``pdf_document`` is provided the
    document is not closed here (worker may reuse it within a document job).
    When ``plan`` is provided (``RenderPlan``), adaptive DPI / embedded policy
    is honoured.
    """

    from backend.app.extraction.visual.page_raster_policy import (
        RenderSourcePolicy,
        extract_embedded_full_page_image,
        inspect_page_rasters,
        plan_render,
    )

    owns_doc = pdf_document is None
    doc: pdfium.PdfDocument | None = pdf_document
    page: pdfium.PdfPage | None = None
    bitmap: pdfium.PdfBitmap | None = None
    try:
        if doc is None:
            doc = pdfium.PdfDocument(str(pdf_path))
        page_count = len(doc)
        if page_number < 1 or page_number > page_count:
            raise VisualOcrError(
                ErrorCode.VISUAL_RENDER_FAILED,
                "Page number is out of range for the canonical PDF.",
                operation="open_page",
                failing_component="renderer",
                page_number=page_number,
            )

        page = doc[page_number - 1]
        # Confirm rendered visual size matches Phase 2 canonical metadata.
        pdf_w, pdf_h = page.get_size()
        tol = limits.dimension_tolerance_points
        width_mismatch = abs(float(pdf_w) - page_width_points) > tol
        height_mismatch = abs(float(pdf_h) - page_height_points) > tol
        if width_mismatch or height_mismatch:
            raise VisualOcrError(
                ErrorCode.VISUAL_RENDER_DIMENSION_MISMATCH,
                "Rendered page dimensions do not match canonical metadata.",
                operation="dimension_check",
                failing_component="renderer",
                page_number=page_number,
            )

        if plan is None:
            assessment = inspect_page_rasters(
                page,
                page_width_points=page_width_points,
                page_height_points=page_height_points,
            )
            plan = plan_render(
                assessment,
                page_width_points=page_width_points,
                page_height_points=page_height_points,
                requested_dpi=limits.target_dpi,
                min_effective_dpi=limits.min_effective_dpi,
                max_render_pixels=limits.max_render_pixels,
                max_render_side_pixels=limits.max_render_side_pixels,
                # Prefer capped pdfium render: embedded decode is fragile on some
                # Windows pdfium builds (finalizer crashes). Cap still prevents upscale.
                prefer_embedded=False,
            )

        effective_dpi = float(plan.effective_dpi)
        render_scale = effective_dpi / _POINTS_PER_INCH
        expected_w, expected_h = _expected_pixel_size(
            page_width_points, page_height_points, effective_dpi
        )

        image: Image.Image
        if plan.policy is RenderSourcePolicy.EMBEDDED_FULL_PAGE_IMAGE and plan.embedded is not None:
            try:
                image = extract_embedded_full_page_image(page, embedded=plan.embedded)
                # Downscale only if source exceeds resource caps (never upscale).
                max_side = limits.max_render_side_pixels
                w, h = image.size
                pixels = w * h
                if w > max_side or h > max_side or pixels > limits.max_render_pixels:
                    scale = min(
                        max_side / max(w, 1),
                        max_side / max(h, 1),
                        (limits.max_render_pixels / max(pixels, 1)) ** 0.5,
                    )
                    if scale < 1.0:
                        new_size = (
                            max(1, int(w * scale)),
                            max(1, int(h * scale)),
                        )
                        image = image.resize(new_size, Image.Resampling.BILINEAR)
                        plan = replace(
                            plan,
                            downscale_reason="embedded_resource_cap",
                            effective_dpi=effective_dpi * scale,
                        )
                        effective_dpi = float(plan.effective_dpi)
            except Exception:
                # Fall back to pdfium at the planned DPI.
                bitmap = page.render(
                    scale=render_scale,
                    rotation=0,
                    rev_byteorder=True,
                    limit_image_cache=True,
                    may_draw_forms=True,
                    draw_annots=True,
                    fill_color=(255, 255, 255, 255),
                )
                shared = bitmap.to_pil()
                image = shared.copy()
                bitmap.close()
                bitmap = None
                shared.close()
                plan = replace(
                    plan,
                    policy=(
                        RenderSourcePolicy.PDFIUM_RENDER_CAPPED_TO_SOURCE_RESOLUTION
                        if plan.source_resolution_cap_applied
                        else RenderSourcePolicy.PDFIUM_RENDER
                    ),
                    downscale_reason=plan.downscale_reason or "embedded_decode_fallback",
                )
        else:
            bitmap = page.render(
                scale=render_scale,
                rotation=0,
                rev_byteorder=True,
                limit_image_cache=True,
                may_draw_forms=True,
                draw_annots=True,
                fill_color=(255, 255, 255, 255),
            )
            shared = bitmap.to_pil()
            image = shared.copy()
            bitmap.close()
            bitmap = None
            shared.close()

        if image.mode not in {"RGB", "RGBA", "L"}:
            image = image.convert("RGBA")

        width_pixels, height_pixels = image.size
        if plan.policy is not RenderSourcePolicy.EMBEDDED_FULL_PAGE_IMAGE and (
            abs(width_pixels - expected_w) > 2 or abs(height_pixels - expected_h) > 2
        ):
            rel_w = abs(width_pixels - expected_w) / max(expected_w, 1)
            rel_h = abs(height_pixels - expected_h) / max(expected_h, 1)
            if rel_w > 0.02 or rel_h > 0.02:
                raise VisualOcrError(
                    ErrorCode.VISUAL_RENDER_DIMENSION_MISMATCH,
                    "Rendered pixel dimensions diverge from canonical geometry.",
                    operation="pixel_dimension_check",
                    failing_component="renderer",
                    page_number=page_number,
                )

        logger.info(
            "Rendered page",
            extra={
                "page_number": page_number,
                "width_pixels": width_pixels,
                "height_pixels": height_pixels,
                "effective_dpi": effective_dpi,
                "requested_dpi": plan.requested_dpi,
                "render_source_policy": plan.policy.value,
                "downscale_reason": plan.downscale_reason,
                "source_resolution_cap_applied": plan.source_resolution_cap_applied,
                "source_width_px": plan.source_width_px,
                "source_height_px": plan.source_height_px,
            },
        )
        return RenderedPage(
            page_number=page_number,
            image=image,
            width_pixels=width_pixels,
            height_pixels=height_pixels,
            effective_dpi=effective_dpi,
            render_scale=render_scale,
            page_width_points=page_width_points,
            page_height_points=page_height_points,
            requested_dpi=float(plan.requested_dpi),
            render_source_policy=plan.policy.value,
            downscale_reason=plan.downscale_reason,
            source_resolution_cap_applied=bool(plan.source_resolution_cap_applied),
            source_width_px=plan.source_width_px,
            source_height_px=plan.source_height_px,
        )
    except VisualOcrError:
        raise
    except Exception as exc:
        raise VisualOcrError(
            ErrorCode.VISUAL_RENDER_FAILED,
            "Page rendering failed.",
            operation="render_page",
            failing_component="renderer",
            page_number=page_number,
            exception_type=type(exc).__name__,
        ) from exc
    finally:
        if bitmap is not None:
            with contextlib.suppress(Exception):
                bitmap.close()
        if page is not None:
            with contextlib.suppress(Exception):
                page.close()
        if owns_doc and doc is not None:
            with contextlib.suppress(Exception):
                doc.close()


def open_document(pdf_path: Path) -> pdfium.PdfDocument:
    """Open a canonical PDF for multi-page rendering within one job."""

    try:
        return pdfium.PdfDocument(str(pdf_path))
    except Exception as exc:
        raise VisualOcrError(
            ErrorCode.VISUAL_RENDER_FAILED,
            "Failed to open canonical PDF for rendering.",
            operation="open_document",
            failing_component="renderer",
            exception_type=type(exc).__name__,
        ) from exc


def flatten_to_rgb(image: Image.Image) -> Image.Image:
    """Flatten transparency onto white and return an RGB image."""

    if image.mode == "RGB":
        return image
    if image.mode == "RGBA" or "A" in image.getbands():
        background = Image.new("RGB", image.size, (255, 255, 255))
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return image.convert("RGB")

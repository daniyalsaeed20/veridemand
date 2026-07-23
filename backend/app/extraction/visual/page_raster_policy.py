"""Full-page raster detection and OCR render-source policy.

Uses generic page geometry only (coverage, dimensions, object counts).
Never uses filenames or content hashes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import pypdfium2 as pdfium
from pypdfium2 import raw as pdfium_raw

_POINTS_PER_INCH = 72.0
_FULL_PAGE_COVERAGE = 0.88
_DIM_MATCH_RATIO = 0.92  # image px vs page points when MediaBox ≈ source pixels


class RenderSourcePolicy(StrEnum):
    """How the OCR bitmap for a page was produced."""

    PDFIUM_RENDER = "pdfium_render"
    EMBEDDED_FULL_PAGE_IMAGE = "embedded_full_page_image"
    PDFIUM_RENDER_CAPPED_TO_SOURCE_RESOLUTION = "pdfium_render_capped_to_source_resolution"


@dataclass(frozen=True, slots=True)
class EmbeddedImageInfo:
    """Privacy-safe metadata for one PDF image XObject on a page."""

    width_px: int
    height_px: int
    coverage_ratio: float
    # Placement in page space (points), origin top-left after normalisation helpers.
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True, slots=True)
class PageRasterAssessment:
    """Evidence used to choose a render-source policy."""

    image_count: int
    largest_coverage_ratio: float
    text_object_count: int
    path_object_count: int
    embedded: EmbeddedImageInfo | None
    is_full_page_raster: bool
    source_width_px: int | None
    source_height_px: int | None


@dataclass(frozen=True, slots=True)
class RenderPlan:
    """Pre-render size plan (no silent quality cuts)."""

    policy: RenderSourcePolicy
    requested_dpi: float
    target_dpi: float
    effective_dpi: float
    downscale_reason: str | None
    source_resolution_cap_applied: bool
    source_width_px: int | None
    source_height_px: int | None
    canonical_width_points: float
    canonical_height_points: float
    embedded: EmbeddedImageInfo | None


def _page_object_counts(page: pdfium.PdfPage) -> tuple[int, int, int]:
    """Return (image_count, text_count, path_count)."""

    images = 0
    texts = 0
    paths = 0
    for obj in page.get_objects():
        try:
            obj_type = int(obj.type)
        except Exception:
            continue
        if obj_type == int(pdfium_raw.FPDF_PAGEOBJ_IMAGE):
            images += 1
        elif obj_type == int(pdfium_raw.FPDF_PAGEOBJ_TEXT):
            texts += 1
        elif obj_type == int(pdfium_raw.FPDF_PAGEOBJ_PATH):
            paths += 1
    return images, texts, paths


def _coverage_from_bounds(
    bounds: tuple[float, float, float, float],
    *,
    page_width: float,
    page_height: float,
) -> tuple[float, float, float, float, float]:
    """Return coverage_ratio and clipped x0,y0,x1,y1 in top-left page space.

    PDFium bounds are typically left, bottom, right, top in PDF user space
    (origin bottom-left). Convert y to top-left for consistent logging.
    """

    left, bottom, right, top = bounds
    x0 = max(0.0, min(float(left), float(right)))
    x1 = min(page_width, max(float(left), float(right)))
    # PDF y: bottom < top in user space usually; convert to top-origin.
    y_top_pdf = max(float(bottom), float(top))
    y_bottom_pdf = min(float(bottom), float(top))
    y0 = max(0.0, page_height - y_top_pdf)
    y1 = min(page_height, page_height - y_bottom_pdf)
    if x1 <= x0 or y1 <= y0:
        return 0.0, x0, y0, x1, y1
    area = (x1 - x0) * (y1 - y0)
    page_area = max(page_width * page_height, 1.0)
    return min(1.0, area / page_area), x0, y0, x1, y1


def inspect_page_rasters(
    page: pdfium.PdfPage,
    *,
    page_width_points: float,
    page_height_points: float,
) -> PageRasterAssessment:
    """Inspect embedded images without decoding pixel payloads into OCR yet."""

    image_count, text_count, path_count = _page_object_counts(page)
    best: EmbeddedImageInfo | None = None
    best_coverage = 0.0

    for obj in page.get_objects(max_depth=2):
        try:
            if int(obj.type) != int(pdfium_raw.FPDF_PAGEOBJ_IMAGE):
                continue
        except Exception:
            continue
        try:
            image = pdfium.PdfImage(obj)
            width_px, height_px = image.get_px_size()
        except Exception:
            continue

        coverage = 0.0
        x0 = y0 = 0.0
        x1 = page_width_points
        y1 = page_height_points
        try:
            bounds = image.get_bounds()
            coverage, x0, y0, x1, y1 = _coverage_from_bounds(
                bounds,
                page_width=page_width_points,
                page_height=page_height_points,
            )
        except Exception:
            # Loose page objects may not expose bounds; fall back to dimension match.
            w_ratio = float(width_px) / max(page_width_points, 1.0)
            h_ratio = float(height_px) / max(page_height_points, 1.0)
            if w_ratio >= _DIM_MATCH_RATIO and h_ratio >= _DIM_MATCH_RATIO:
                coverage = min(1.0, w_ratio * h_ratio)
            else:
                coverage = min(1.0, w_ratio * h_ratio * 0.5)

        info = EmbeddedImageInfo(
            width_px=int(width_px),
            height_px=int(height_px),
            coverage_ratio=coverage,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
        )
        if coverage >= best_coverage:
            best_coverage = coverage
            best = info

    is_full = False
    if best is not None and image_count == 1:
        w_ratio = best.width_px / max(page_width_points, 1.0)
        h_ratio = best.height_px / max(page_height_points, 1.0)
        dim_match = w_ratio >= _DIM_MATCH_RATIO and h_ratio >= _DIM_MATCH_RATIO
        sparse_vectors = text_count <= 2
        is_full = (best.coverage_ratio >= _FULL_PAGE_COVERAGE and sparse_vectors) or (
            dim_match and sparse_vectors
        )

    return PageRasterAssessment(
        image_count=image_count,
        largest_coverage_ratio=best_coverage,
        text_object_count=text_count,
        path_object_count=path_count,
        embedded=best,
        is_full_page_raster=is_full,
        source_width_px=best.width_px if best else None,
        source_height_px=best.height_px if best else None,
    )


def plan_render(
    assessment: PageRasterAssessment,
    *,
    page_width_points: float,
    page_height_points: float,
    requested_dpi: float,
    min_effective_dpi: float,
    max_render_pixels: int,
    max_render_side_pixels: int,
    prefer_embedded: bool = True,
) -> RenderPlan:
    """Choose render policy and target DPI before producing a bitmap."""

    from backend.app.extraction.visual.renderer import compute_effective_dpi

    source_w = assessment.source_width_px
    source_h = assessment.source_height_px
    downscale_reason: str | None = None
    source_cap = False
    policy = RenderSourcePolicy.PDFIUM_RENDER
    target = float(requested_dpi)

    if assessment.is_full_page_raster and source_w and source_h:
        # DPI that maps page points to at most source pixels (no upscale).
        dpi_from_w = source_w * _POINTS_PER_INCH / max(page_width_points, 1.0)
        dpi_from_h = source_h * _POINTS_PER_INCH / max(page_height_points, 1.0)
        source_dpi = min(dpi_from_w, dpi_from_h)
        if prefer_embedded and assessment.embedded is not None:
            policy = RenderSourcePolicy.EMBEDDED_FULL_PAGE_IMAGE
            target = min(float(requested_dpi), source_dpi)
            if target + 1e-6 < float(requested_dpi):
                source_cap = True
                downscale_reason = "source_resolution_cap_no_upscale"
        else:
            policy = RenderSourcePolicy.PDFIUM_RENDER_CAPPED_TO_SOURCE_RESOLUTION
            target = min(float(requested_dpi), source_dpi)
            source_cap = target + 1e-6 < float(requested_dpi)
            downscale_reason = "source_resolution_cap_no_upscale" if source_cap else None

    # Never go below a tiny floor for embedded 1:1 scans; allow below configured
    # min_effective_dpi when source-capping (72 DPI identity scans).
    floor = float(min_effective_dpi)
    if policy != RenderSourcePolicy.PDFIUM_RENDER and source_cap:
        floor = min(floor, max(36.0, target * 0.5))

    try:
        effective = compute_effective_dpi(
            page_width_points=page_width_points,
            page_height_points=page_height_points,
            target_dpi=max(target, 1.0),
            min_effective_dpi=max(1.0, floor),
            max_render_pixels=max_render_pixels,
            max_render_side_pixels=max_render_side_pixels,
        )
    except Exception:
        # Fall back to pdfium render with standard caps.
        policy = RenderSourcePolicy.PDFIUM_RENDER
        effective = compute_effective_dpi(
            page_width_points=page_width_points,
            page_height_points=page_height_points,
            target_dpi=float(requested_dpi),
            min_effective_dpi=float(min_effective_dpi),
            max_render_pixels=max_render_pixels,
            max_render_side_pixels=max_render_side_pixels,
        )
        downscale_reason = "resource_cap_fallback"
        source_cap = False

    if effective + 1e-6 < target and downscale_reason is None:
        downscale_reason = "resource_pixel_or_side_cap"

    return RenderPlan(
        policy=policy,
        requested_dpi=float(requested_dpi),
        target_dpi=float(target),
        effective_dpi=float(effective),
        downscale_reason=downscale_reason,
        source_resolution_cap_applied=source_cap,
        source_width_px=source_w,
        source_height_px=source_h,
        canonical_width_points=page_width_points,
        canonical_height_points=page_height_points,
        embedded=assessment.embedded,
    )


def extract_embedded_full_page_image(
    page: pdfium.PdfPage,
    *,
    embedded: EmbeddedImageInfo,
) -> Any:
    """Decode the embedded full-page raster as a PIL RGB image (caller owns it)."""

    from PIL import Image

    for obj in page.get_objects():
        try:
            if int(obj.type) != int(pdfium_raw.FPDF_PAGEOBJ_IMAGE):
                continue
        except Exception:
            continue
        try:
            image = pdfium.PdfImage(obj)
            width_px, height_px = image.get_px_size()
        except Exception:
            continue
        if int(width_px) != embedded.width_px or int(height_px) != embedded.height_px:
            continue
        try:
            bitmap = image.get_bitmap(render=False, scale_to_original=True)
            pil = bitmap.to_pil().copy()
            bitmap.close()
        except Exception:
            # JPEG/JBIG may need extract path.
            try:
                data = image.get_data()
                from io import BytesIO

                pil = Image.open(BytesIO(data)).convert("RGB")
            except Exception as exc:
                raise RuntimeError(f"embedded_image_decode_failed:{type(exc).__name__}") from exc
        if pil.mode != "RGB":
            if pil.mode in {"RGBA", "LA"} or "A" in pil.getbands():
                background = Image.new("RGB", pil.size, (255, 255, 255))
                rgba = pil.convert("RGBA")
                background.paste(rgba, mask=rgba.split()[-1])
                pil = background
            else:
                pil = pil.convert("RGB")
        return pil
    raise RuntimeError("embedded_full_page_image_not_found")

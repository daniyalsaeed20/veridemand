"""Full-page raster detection and OCR render-source policy.

Uses generic page geometry only (coverage, dimensions, object counts).
Never uses filenames or content hashes. Image metadata is read via ``pypdf``
(not pdfium PdfImage) to avoid native finalizer crashes observed on CI.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

_POINTS_PER_INCH = 72.0
_FULL_PAGE_COVERAGE = 0.88
_DIM_MATCH_RATIO = 0.92  # image px vs page points when MediaBox ~= source pixels


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


def inspect_page_rasters_from_pdf(
    pdf_path: Path,
    *,
    page_number: int,
    page_width_points: float,
    page_height_points: float,
) -> PageRasterAssessment:
    """Inspect embedded images with pypdf (1-based page_number)."""

    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    if page_number < 1 or page_number > len(reader.pages):
        return PageRasterAssessment(0, 0.0, 0, 0, None, False, None, None)

    page = reader.pages[page_number - 1]
    resources = page.get("/Resources")
    if resources is None:
        return PageRasterAssessment(0, 0.0, 0, 0, None, False, None, None)
    resources = resources.get_object()
    xobjects = resources.get("/XObject") if resources else None
    images: list[EmbeddedImageInfo] = []
    if xobjects is not None:
        xobjects = xobjects.get_object()
        for _name, ref in xobjects.items():
            try:
                obj = ref.get_object()
            except Exception:
                continue
            if str(obj.get("/Subtype", "")) != "/Image":
                continue
            try:
                width_px = int(obj["/Width"])
                height_px = int(obj["/Height"])
            except Exception:
                continue
            # Without a placement box, treat a single near page-sized image as full-page.
            w_ratio = width_px / max(page_width_points, 1.0)
            h_ratio = height_px / max(page_height_points, 1.0)
            coverage = min(1.0, w_ratio * h_ratio) if w_ratio >= 0.5 and h_ratio >= 0.5 else 0.0
            images.append(
                EmbeddedImageInfo(
                    width_px=width_px,
                    height_px=height_px,
                    coverage_ratio=coverage,
                    x0=0.0,
                    y0=0.0,
                    x1=page_width_points,
                    y1=page_height_points,
                )
            )

    # Text operator presence is approximated: empty ExtractText => sparse.
    try:
        extracted = page.extract_text() or ""
        text_object_count = 0 if not extracted.strip() else max(1, extracted.count("\n") + 1)
    except Exception:
        text_object_count = 0

    best = max(images, key=lambda item: item.coverage_ratio) if images else None
    best_coverage = best.coverage_ratio if best else 0.0
    is_full = False
    if best is not None and len(images) == 1:
        w_ratio = best.width_px / max(page_width_points, 1.0)
        h_ratio = best.height_px / max(page_height_points, 1.0)
        dim_match = w_ratio >= _DIM_MATCH_RATIO and h_ratio >= _DIM_MATCH_RATIO
        sparse = text_object_count <= 2
        is_full = (best_coverage >= _FULL_PAGE_COVERAGE and sparse) or (dim_match and sparse)

    return PageRasterAssessment(
        image_count=len(images),
        largest_coverage_ratio=best_coverage,
        text_object_count=text_object_count,
        path_object_count=0,
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
    prefer_embedded: bool = False,
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
        dpi_from_w = source_w * _POINTS_PER_INCH / max(page_width_points, 1.0)
        dpi_from_h = source_h * _POINTS_PER_INCH / max(page_height_points, 1.0)
        source_dpi = min(dpi_from_w, dpi_from_h)
        if prefer_embedded and assessment.embedded is not None:
            policy = RenderSourcePolicy.EMBEDDED_FULL_PAGE_IMAGE
        else:
            policy = RenderSourcePolicy.PDFIUM_RENDER_CAPPED_TO_SOURCE_RESOLUTION
        target = min(float(requested_dpi), source_dpi)
        source_cap = target + 1e-6 < float(requested_dpi)
        downscale_reason = "source_resolution_cap_no_upscale" if source_cap else None

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
    pdf_path: Path,
    *,
    page_number: int,
    embedded: EmbeddedImageInfo,
) -> Any:
    """Decode the largest matching embedded image via pypdf (caller owns PIL image)."""

    from io import BytesIO

    from PIL import Image
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    page = reader.pages[page_number - 1]
    resources = page.get("/Resources")
    if resources is None:
        raise RuntimeError("embedded_full_page_image_not_found")
    resources = resources.get_object()
    xobjects = resources.get("/XObject")
    if xobjects is None:
        raise RuntimeError("embedded_full_page_image_not_found")
    xobjects = xobjects.get_object()
    for _name, ref in xobjects.items():
        obj = ref.get_object()
        if str(obj.get("/Subtype", "")) != "/Image":
            continue
        if int(obj["/Width"]) != embedded.width_px or int(obj["/Height"]) != embedded.height_px:
            continue
        data = obj.get_data()
        # DCTDecode JPEG often opens directly; FlateDecode may need filters.
        try:
            pil = Image.open(BytesIO(data))
            pil.load()
        except Exception:
            # Fallback: reconstruct from raw samples when possible.
            mode = "RGB"
            color_space = str(obj.get("/ColorSpace", ""))
            if "Gray" in color_space:
                mode = "L"
            pil = Image.frombytes(mode, (embedded.width_px, embedded.height_px), data)
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

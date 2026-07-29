"""Coordinate transforms for targeted-repair crops.

Chain:
  canonical normalised → PDF points → rendered pixels → crop pixels
  → repaired local polygons → rendered pixels → canonical normalised
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from backend.app.contracts.geometry import (
    Geometry,
    NormalisedBoundingBox,
    NormalisedPolygon,
)
from backend.app.contracts.ocr import PixelBoundingBox, PixelPolygon
from backend.app.extraction.visual.coordinates import map_pixel_polygon


@dataclass(frozen=True, slots=True)
class RepairCropTransform:
    """Maps between crop-local pixels and full-page rendered pixels."""

    page_width_px: int
    page_height_px: int
    crop_x0_px: int
    crop_y0_px: int
    crop_width_px: int
    crop_height_px: int
    expanded_bbox: NormalisedBoundingBox
    # Canonical page size in PDF points (MediaBox / CropBox aware via caller).
    page_width_points: float
    page_height_points: float
    render_scale: float
    intrinsic_rotation: int = 0

    @property
    def crop_box_px(self) -> tuple[int, int, int, int]:
        return (
            self.crop_x0_px,
            self.crop_y0_px,
            self.crop_x0_px + self.crop_width_px,
            self.crop_y0_px + self.crop_height_px,
        )


def _clamp01(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("Non-finite coordinate in repair transform.")
    return max(0.0, min(1.0, value))


def normalised_to_pdf_points(
    x: float,
    y: float,
    *,
    width_points: float,
    height_points: float,
) -> tuple[float, float]:
    """Map top-left normalised coords to PDF points (top-left origin)."""

    return (_clamp01(x) * width_points, _clamp01(y) * height_points)


def pdf_points_to_normalised(
    x_pt: float,
    y_pt: float,
    *,
    width_points: float,
    height_points: float,
) -> tuple[float, float]:
    if width_points <= 0 or height_points <= 0:
        raise ValueError("Page point dimensions must be positive.")
    return (_clamp01(x_pt / width_points), _clamp01(y_pt / height_points))


def normalised_bbox_to_pixel_crop(
    bbox: NormalisedBoundingBox,
    *,
    page_width_px: int,
    page_height_px: int,
) -> tuple[int, int, int, int]:
    """Convert normalised bbox to inclusive-exclusive pixel crop bounds."""

    if page_width_px < 1 or page_height_px < 1:
        raise ValueError("Render dimensions must be positive.")
    x0 = int(max(0, math.floor(bbox.x * page_width_px)))
    y0 = int(max(0, math.floor(bbox.y * page_height_px)))
    x1 = int(min(page_width_px, math.ceil((bbox.x + bbox.width) * page_width_px)))
    y1 = int(min(page_height_px, math.ceil((bbox.y + bbox.height) * page_height_px)))
    if x1 - x0 < 2:
        x1 = min(page_width_px, x0 + 2)
    if y1 - y0 < 2:
        y1 = min(page_height_px, y0 + 2)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("Pixel crop has non-positive area.")
    return x0, y0, x1, y1


def build_crop_transform(
    expanded_bbox: NormalisedBoundingBox,
    *,
    page_width_px: int,
    page_height_px: int,
    page_width_points: float,
    page_height_points: float,
    render_scale: float,
    intrinsic_rotation: int = 0,
) -> RepairCropTransform:
    """Build the full crop transform, applying intrinsic rotation exactly once upstream."""

    # Rotation must already be applied in the rendered image; record for audit only.
    rot = int(intrinsic_rotation) % 360
    if rot not in {0, 90, 180, 270}:
        rot = 0
    x0, y0, x1, y1 = normalised_bbox_to_pixel_crop(
        expanded_bbox,
        page_width_px=page_width_px,
        page_height_px=page_height_px,
    )
    return RepairCropTransform(
        page_width_px=page_width_px,
        page_height_px=page_height_px,
        crop_x0_px=x0,
        crop_y0_px=y0,
        crop_width_px=x1 - x0,
        crop_height_px=y1 - y0,
        expanded_bbox=expanded_bbox,
        page_width_points=page_width_points,
        page_height_points=page_height_points,
        render_scale=render_scale,
        intrinsic_rotation=rot,
    )


def crop_local_to_page_pixels(
    points_crop_px: list[tuple[float, float]],
    transform: RepairCropTransform,
) -> list[tuple[float, float]]:
    """Offset crop-local pixel polygons into full-page rendered pixel space."""

    out: list[tuple[float, float]] = []
    for x, y in points_crop_px:
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("Non-finite crop-local polygon point.")
        px = transform.crop_x0_px + x
        py = transform.crop_y0_px + y
        # Clamp softly into page bounds.
        px = max(0.0, min(float(transform.page_width_px), px))
        py = max(0.0, min(float(transform.page_height_px), py))
        out.append((px, py))
    return out


def map_repaired_crop_polygon(
    points_crop_px: list[tuple[float, float]],
    transform: RepairCropTransform,
) -> tuple[NormalisedPolygon, NormalisedBoundingBox, Geometry, PixelPolygon, PixelBoundingBox]:
    """Map a repaired crop-local polygon into canonical normalised geometry."""

    page_pts = crop_local_to_page_pixels(points_crop_px, transform)
    mapped = map_pixel_polygon(
        page_pts,
        width_pixels=transform.page_width_px,
        height_pixels=transform.page_height_px,
    )
    return (
        mapped.polygon,
        mapped.bbox,
        mapped.geometry,
        mapped.pixel_polygon,
        mapped.pixel_bbox,
    )


def word_bbox_to_crop_pixels(
    bbox: NormalisedBoundingBox,
    transform: RepairCropTransform,
) -> tuple[int, int, int, int]:
    """Map a normalised word bbox into crop-local pixel bounds for recognition-only."""

    x0, y0, x1, y1 = normalised_bbox_to_pixel_crop(
        bbox,
        page_width_px=transform.page_width_px,
        page_height_px=transform.page_height_px,
    )
    lx0 = max(0, x0 - transform.crop_x0_px)
    ly0 = max(0, y0 - transform.crop_y0_px)
    lx1 = min(transform.crop_width_px, x1 - transform.crop_x0_px)
    ly1 = min(transform.crop_height_px, y1 - transform.crop_y0_px)
    if lx1 - lx0 < 2:
        lx1 = min(transform.crop_width_px, lx0 + 2)
    if ly1 - ly0 < 2:
        ly1 = min(transform.crop_height_px, ly0 + 2)
    return lx0, ly0, lx1, ly1

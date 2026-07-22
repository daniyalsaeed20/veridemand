"""Map Paddle pixel polygons into VeriDemand normalised geometry."""

from __future__ import annotations

import math
from dataclasses import dataclass

from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.geometry import (
    Geometry,
    NormalisedBoundingBox,
    NormalisedPoint,
    NormalisedPolygon,
)
from backend.app.contracts.ocr import PixelBoundingBox, PixelPolygon
from backend.app.extraction.visual.errors import VisualOcrError

_FP_TOLERANCE = 1e-6


@dataclass(frozen=True, slots=True)
class MappedPixelGeometry:
    """Pixel and normalised geometry for one OCR object."""

    pixel_polygon: PixelPolygon
    pixel_bbox: PixelBoundingBox
    polygon: NormalisedPolygon
    bbox: NormalisedBoundingBox
    geometry: Geometry


def _finite(*values: float) -> bool:
    return all(math.isfinite(v) for v in values)


def _bbox_from_points(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    left = min(xs)
    top = min(ys)
    right = max(xs)
    bottom = max(ys)
    return left, top, right, bottom


def map_pixel_polygon(
    points_px: list[tuple[float, float]],
    *,
    width_pixels: int,
    height_pixels: int,
) -> MappedPixelGeometry:
    """Convert top-left pixel polygon into validated normalised geometry."""

    if width_pixels <= 0 or height_pixels <= 0:
        raise VisualOcrError(
            ErrorCode.VISUAL_GEOMETRY_INVALID,
            "Render dimensions are invalid for coordinate mapping.",
            operation="map_pixel_polygon",
            failing_component="coordinates",
        )
    if len(points_px) < 3:
        raise VisualOcrError(
            ErrorCode.VISUAL_GEOMETRY_INVALID,
            "OCR polygon must contain at least three points.",
            operation="map_pixel_polygon",
            failing_component="coordinates",
        )
    for x, y in points_px:
        if not _finite(x, y):
            raise VisualOcrError(
                ErrorCode.VISUAL_GEOMETRY_INVALID,
                "OCR polygon contains non-finite coordinates.",
                operation="map_pixel_polygon",
                failing_component="coordinates",
            )

    left, top, right, bottom = _bbox_from_points(points_px)
    if right - left <= 0 or bottom - top <= 0:
        raise VisualOcrError(
            ErrorCode.VISUAL_GEOMETRY_INVALID,
            "OCR polygon has zero area.",
            operation="map_pixel_polygon",
            failing_component="coordinates",
        )

    # Material out-of-bounds rejection (beyond tiny FP overflow).
    for x, y in points_px:
        if x < -1.0 or y < -1.0 or x > width_pixels + 1.0 or y > height_pixels + 1.0:
            raise VisualOcrError(
                ErrorCode.VISUAL_GEOMETRY_INVALID,
                "OCR polygon is materially outside the rendered page.",
                operation="map_pixel_polygon",
                failing_component="coordinates",
            )

    def norm(x: float, y: float) -> tuple[float, float]:
        nx = x / float(width_pixels)
        ny = y / float(height_pixels)
        # Clamp tiny FP overflow only.
        if -_FP_TOLERANCE <= nx < 0.0:
            nx = 0.0
        if -_FP_TOLERANCE <= ny < 0.0:
            ny = 0.0
        if 1.0 < nx <= 1.0 + _FP_TOLERANCE:
            nx = 1.0
        if 1.0 < ny <= 1.0 + _FP_TOLERANCE:
            ny = 1.0
        if nx < 0.0 or ny < 0.0 or nx > 1.0 or ny > 1.0:
            raise VisualOcrError(
                ErrorCode.VISUAL_GEOMETRY_INVALID,
                "Normalised OCR point is out of bounds.",
                operation="map_pixel_polygon",
                failing_component="coordinates",
            )
        return nx, ny

    normalised_pts = [norm(x, y) for x, y in points_px]
    # Ensure closed-ish distinct points for Geometry validation.
    unique: list[tuple[float, float]] = []
    for pt in normalised_pts:
        if not unique or abs(unique[-1][0] - pt[0]) > 1e-12 or abs(unique[-1][1] - pt[1]) > 1e-12:
            unique.append(pt)
    if len(unique) < 3:
        raise VisualOcrError(
            ErrorCode.VISUAL_GEOMETRY_INVALID,
            "OCR polygon collapsed after normalisation.",
            operation="map_pixel_polygon",
            failing_component="coordinates",
        )

    nxs = [p[0] for p in unique]
    nys = [p[1] for p in unique]
    nx0, ny0 = min(nxs), min(nys)
    nx1, ny1 = max(nxs), max(nys)
    nw = max(nx1 - nx0, 1e-9)
    nh = max(ny1 - ny0, 1e-9)
    # Keep bbox inside the unit square.
    if nx0 + nw > 1.0:
        nw = 1.0 - nx0
    if ny0 + nh > 1.0:
        nh = 1.0 - ny0
    if nw <= 0.0 or nh <= 0.0:
        raise VisualOcrError(
            ErrorCode.VISUAL_GEOMETRY_INVALID,
            "Normalised OCR bbox has zero area.",
            operation="map_pixel_polygon",
            failing_component="coordinates",
        )

    polygon = NormalisedPolygon(points=[NormalisedPoint(x=x, y=y) for x, y in unique])
    bbox = NormalisedBoundingBox(x=nx0, y=ny0, width=nw, height=nh)
    geometry = Geometry(polygon=polygon, bbox=bbox)

    pixel_polygon = PixelPolygon(points=[(float(x), float(y)) for x, y in points_px])
    pixel_bbox = PixelBoundingBox(
        x=float(left),
        y=float(top),
        width=float(right - left),
        height=float(bottom - top),
    )
    return MappedPixelGeometry(
        pixel_polygon=pixel_polygon,
        pixel_bbox=pixel_bbox,
        polygon=polygon,
        bbox=bbox,
        geometry=geometry,
    )


def normalised_to_page_points(
    *,
    normalised_x: float,
    normalised_y: float,
    page_width_points: float,
    page_height_points: float,
) -> tuple[float, float]:
    """Map normalised coordinates back to canonical page points."""

    return normalised_x * page_width_points, normalised_y * page_height_points

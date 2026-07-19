"""Coordinate normalization for native PDF extraction (top-left [0,1])."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.geometry import normalize_polygon, validate_normalized_polygon


@dataclass(frozen=True)
class PageGeometry:
    """Visible page box in PDF user space (origin bottom-left before flip)."""

    width: float
    height: float
    crop_x0: float = 0.0
    crop_y0: float = 0.0
    rotation: int = 0  # 0, 90, 180, 270


def pdfplumber_bbox_to_normalized_quad(
    x0: float,
    top: float,
    x1: float,
    bottom: float,
    geom: PageGeometry,
) -> list[list[float]] | None:
    """Convert pdfplumber top-left bbox into a normalized quad.

    pdfplumber word boxes use top-left origin with ``top`` / ``bottom``
    already relative to the page top. Values outside the page produce None
    (caller should warn rather than emit a misleading highlight).
    """
    if geom.width <= 0 or geom.height <= 0:
        return None

    # Translate by crop origin if crop box inset was applied to dimensions
    rel_x0 = (x0 - geom.crop_x0) / geom.width
    rel_x1 = (x1 - geom.crop_x0) / geom.width
    rel_y0 = top / geom.height
    rel_y1 = bottom / geom.height

    # Apply display rotation about page center in normalized space
    points = [
        (rel_x0, rel_y0),
        (rel_x1, rel_y0),
        (rel_x1, rel_y1),
        (rel_x0, rel_y1),
    ]
    points = [_rotate_normalized(px, py, geom.rotation) for px, py in points]

    try:
        validate_normalized_polygon(points)
    except ValueError:
        # Soft clamp then re-validate; if still invalid, reject
        clamped = [(_clamp01(px), _clamp01(py)) for px, py in points]
        try:
            validate_normalized_polygon(clamped)
            # If clamping moved a point, treat as warning path when drift is large
            if any(
                abs(a[0] - b[0]) > 0.02 or abs(a[1] - b[1]) > 0.02
                for a, b in zip(points, clamped, strict=True)
            ):
                return None
            return [[x, y] for x, y in clamped]
        except ValueError:
            return None
    return [[x, y] for x, y in points]


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _rotate_normalized(x: float, y: float, rotation: int) -> tuple[float, float]:
    rot = rotation % 360
    if rot == 0:
        return x, y
    if rot == 90:
        return y, 1.0 - x
    if rot == 180:
        return 1.0 - x, 1.0 - y
    if rot == 270:
        return 1.0 - y, x
    return x, y


def screen_rect_from_normalized(
    polygon: list[list[float]],
    *,
    rendered_width: float,
    rendered_height: float,
) -> tuple[float, float, float, float]:
    """Map a normalized polygon to a screen-space axis-aligned rect (x, y, w, h)."""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    left = min(xs) * rendered_width
    top = min(ys) * rendered_height
    right = max(xs) * rendered_width
    bottom = max(ys) * rendered_height
    return left, top, right - left, bottom - top


def absolute_to_normalized(
    points: list[tuple[float, float]],
    *,
    page_width: float,
    page_height: float,
) -> list[tuple[float, float]]:
    return normalize_polygon(points, page_width, page_height)


def image_polygon_to_normalized(
    polygon_px: list[tuple[float, float]],
    *,
    image_width: int,
    image_height: int,
    page_rotation: int = 0,
    clamp: bool = True,
) -> list[list[float]] | None:
    """Map OCR pixel polygons (top-left image space) to canonical [0,1] page space.

    Rendered images from PDFium already incorporate page rotation into the bitmap.
    ``page_rotation`` is retained for callers that need additional display alignment;
    when the bitmap matches the PDF.js viewer orientation, pass ``0``.
    """
    if image_width <= 0 or image_height <= 0:
        return None
    if len(polygon_px) < 3:
        return None

    # Reject degenerate (zero-area) boxes
    xs = [p[0] for p in polygon_px]
    ys = [p[1] for p in polygon_px]
    if max(xs) - min(xs) < 0.5 or max(ys) - min(ys) < 0.5:
        return None

    points: list[tuple[float, float]] = []
    for x, y in polygon_px:
        nx = float(x) / float(image_width)
        ny = float(y) / float(image_height)
        points.append(_rotate_normalized(nx, ny, page_rotation))

    try:
        validate_normalized_polygon(points)
        return [[x, y] for x, y in points]
    except ValueError:
        if not clamp:
            return None
        clamped = [(_clamp01(px), _clamp01(py)) for px, py in points]
        try:
            validate_normalized_polygon(clamped)
        except ValueError:
            return None
        # Large clamp drift → reject rather than mis-highlight
        if any(
            abs(a[0] - b[0]) > 0.05 or abs(a[1] - b[1]) > 0.05
            for a, b in zip(points, clamped, strict=True)
        ):
            return None
        return [[x, y] for x, y in clamped]

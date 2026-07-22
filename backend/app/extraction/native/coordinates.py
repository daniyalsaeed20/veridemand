"""Convert pdfplumber top-origin boxes into VeriDemand canonical geometry."""

from __future__ import annotations

import math
from dataclasses import dataclass

from backend.app.contracts.geometry import (
    Geometry,
    NormalisedBoundingBox,
    NormalisedPoint,
    NormalisedPolygon,
)
from backend.app.contracts.native import PdfPointBox


@dataclass(frozen=True, slots=True)
class MappedBox:
    """Mapped PDF-point and normalised geometry for one object."""

    pdf_point_bbox: PdfPointBox
    geometry: Geometry
    invalid: bool
    out_of_bounds: bool
    zero_area: bool
    clamped: bool


def _finite(*values: float) -> bool:
    return all(math.isfinite(v) for v in values)


def map_pdfplumber_box(
    *,
    x0: float,
    x1: float,
    top: float,
    bottom: float,
    page_bbox_x0: float,
    page_bbox_top: float,
    page_width: float,
    page_height: float,
    coordinate_tolerance_points: float,
) -> MappedBox:
    """Map pdfplumber top-origin fields into canonical coordinates."""

    invalid = False
    out_of_bounds = False
    zero_area = False
    clamped = False

    if not _finite(x0, x1, top, bottom, page_width, page_height, page_bbox_x0, page_bbox_top):
        invalid = True
    if page_width <= 0 or page_height <= 0:
        invalid = True
    if not invalid and (x1 <= x0 or bottom <= top):
        invalid = True
        if abs(x1 - x0) < 1e-12 or abs(bottom - top) < 1e-12:
            zero_area = True

    if invalid:
        # Placeholder geometry rejected by callers; values unused when invalid.
        empty = PdfPointBox(x=0.0, y=0.0, width=1.0, height=1.0)
        geom = Geometry(
            polygon=NormalisedPolygon(
                points=[
                    NormalisedPoint(x=0.0, y=0.0),
                    NormalisedPoint(x=0.01, y=0.0),
                    NormalisedPoint(x=0.01, y=0.01),
                    NormalisedPoint(x=0.0, y=0.01),
                ]
            ),
            bbox=NormalisedBoundingBox(x=0.0, y=0.0, width=0.01, height=0.01),
        )
        return MappedBox(
            pdf_point_bbox=empty,
            geometry=geom,
            invalid=True,
            out_of_bounds=False,
            zero_area=zero_area,
            clamped=False,
        )

    relative_x0 = x0 - page_bbox_x0
    relative_x1 = x1 - page_bbox_x0
    relative_top = top - page_bbox_top
    relative_bottom = bottom - page_bbox_top

    tol = coordinate_tolerance_points

    def clamp_axis(value: float, limit: float) -> tuple[float, bool]:
        if value < -tol or value > limit + tol:
            return value, True  # significant overflow → out of bounds
        if value < 0.0:
            return 0.0, False  # small underflow clamp
        if value > limit:
            return limit, False  # small overflow clamp
        return value, False

    rx0, oob0 = clamp_axis(relative_x0, page_width)
    rx1, oob1 = clamp_axis(relative_x1, page_width)
    rt, oob2 = clamp_axis(relative_top, page_height)
    rb, oob3 = clamp_axis(relative_bottom, page_height)
    significant_oob = oob0 or oob1 or oob2 or oob3

    # Detect whether we applied a small clamp (value changed within tolerance).
    if (
        abs(rx0 - relative_x0) > 1e-15
        or abs(rx1 - relative_x1) > 1e-15
        or abs(rt - relative_top) > 1e-15
        or abs(rb - relative_bottom) > 1e-15
    ) and not significant_oob:
        clamped = True
        relative_x0, relative_x1, relative_top, relative_bottom = rx0, rx1, rt, rb
    elif significant_oob:
        out_of_bounds = True
        relative_x0, relative_x1, relative_top, relative_bottom = rx0, rx1, rt, rb

    width = relative_x1 - relative_x0
    height = relative_bottom - relative_top
    if width <= 0 or height <= 0:
        invalid = True
        zero_area = True

    pdf_box = PdfPointBox(
        x=relative_x0,
        y=relative_top,
        width=max(width, 1e-6),
        height=max(height, 1e-6),
    )

    nx = relative_x0 / page_width
    ny = relative_top / page_height
    nw = width / page_width
    nh = height / page_height

    # Clamp tiny FP overflow into [0,1] for public Geometry validation.
    nx = min(max(nx, 0.0), 1.0)
    ny = min(max(ny, 0.0), 1.0)
    nw = min(max(nw, 0.0), max(1.0 - nx, 1e-9))
    nh = min(max(nh, 0.0), max(1.0 - ny, 1e-9))
    if nw <= 0 or nh <= 0:
        invalid = True
        zero_area = True
        nw = max(nw, 1e-6)
        nh = max(nh, 1e-6)

    geom = Geometry(
        polygon=NormalisedPolygon(
            points=[
                NormalisedPoint(x=nx, y=ny),
                NormalisedPoint(x=nx + nw, y=ny),
                NormalisedPoint(x=nx + nw, y=ny + nh),
                NormalisedPoint(x=nx, y=ny + nh),
            ]
        ),
        bbox=NormalisedBoundingBox(x=nx, y=ny, width=nw, height=nh),
    )
    return MappedBox(
        pdf_point_bbox=pdf_box,
        geometry=geom,
        invalid=invalid,
        out_of_bounds=out_of_bounds,
        zero_area=zero_area,
        clamped=clamped,
    )


def word_contains_characters(
    word_box: PdfPointBox,
    char_boxes: list[PdfPointBox],
    *,
    tolerance_points: float,
) -> bool:
    """Return True when every character box lies inside the word box within tolerance."""

    for box in char_boxes:
        if box.x < word_box.x - tolerance_points:
            return False
        if box.y < word_box.y - tolerance_points:
            return False
        if box.x + box.width > word_box.x + word_box.width + tolerance_points:
            return False
        if box.y + box.height > word_box.y + word_box.height + tolerance_points:
            return False
    return True

"""Normalised geometry contracts (Phase 2).

All display coordinates use a top-left origin, x left→right, y top→bottom,
values in ``[0, 1]``. Intrinsic PDF rotation is already accounted for in the
default visual coordinate system; viewer rotation is applied client-side.
"""

from __future__ import annotations

import math
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from backend.app.contracts.base import ApiModel

_MAX_POLYGON_POINTS = 64
_AREA_EPSILON = 1e-12
_BBOX_CONTAIN_TOLERANCE = 1e-6


def _reject_non_finite(value: float, *, field_name: str) -> float:
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{field_name} must be finite.")
    return value


class NormalisedPoint(ApiModel):
    """A point in normalised page space."""

    x: Annotated[float, Field(ge=0.0, le=1.0)]
    y: Annotated[float, Field(ge=0.0, le=1.0)]

    @field_validator("x", "y")
    @classmethod
    def _finite(cls, value: float) -> float:
        return _reject_non_finite(value, field_name="coordinate")


class NormalisedBoundingBox(ApiModel):
    """Axis-aligned box in normalised page space (top-left origin)."""

    x: Annotated[float, Field(ge=0.0, le=1.0)]
    y: Annotated[float, Field(ge=0.0, le=1.0)]
    width: Annotated[float, Field(gt=0.0, le=1.0)]
    height: Annotated[float, Field(gt=0.0, le=1.0)]

    @field_validator("x", "y", "width", "height")
    @classmethod
    def _finite(cls, value: float) -> float:
        return _reject_non_finite(value, field_name="bbox value")

    @model_validator(mode="after")
    def _within_page(self) -> NormalisedBoundingBox:
        if self.x + self.width > 1.0 + 1e-9:
            raise ValueError("Bounding box crosses the right page boundary.")
        if self.y + self.height > 1.0 + 1e-9:
            raise ValueError("Bounding box crosses the bottom page boundary.")
        # Clamp public serialisation into [0, 1] cleanly.
        object.__setattr__(self, "x", min(max(self.x, 0.0), 1.0))
        object.__setattr__(self, "y", min(max(self.y, 0.0), 1.0))
        object.__setattr__(self, "width", min(max(self.width, 0.0), 1.0 - self.x))
        object.__setattr__(self, "height", min(max(self.height, 0.0), 1.0 - self.y))
        if self.width <= 0.0 or self.height <= 0.0:
            raise ValueError("Bounding box width and height must remain positive after clamp.")
        return self


class NormalisedPolygon(ApiModel):
    """Closed polygon in normalised page space (at least three points)."""

    points: list[NormalisedPoint] = Field(min_length=3, max_length=_MAX_POLYGON_POINTS)

    @model_validator(mode="after")
    def _validate_polygon(self) -> NormalisedPolygon:
        pts = self.points
        for i in range(len(pts)):
            a = pts[i]
            b = pts[(i + 1) % len(pts)]
            if abs(a.x - b.x) < 1e-12 and abs(a.y - b.y) < 1e-12 and i < len(pts) - 1:
                # Adjacent duplicates (excluding intentional close of first/last if equal).
                raise ValueError("Polygon must not contain adjacent duplicate points.")
        # Shoelace area (absolute).
        area = 0.0
        for i in range(len(pts)):
            x1, y1 = pts[i].x, pts[i].y
            x2, y2 = pts[(i + 1) % len(pts)].x, pts[(i + 1) % len(pts)].y
            area += x1 * y2 - x2 * y1
        if abs(area) / 2.0 <= _AREA_EPSILON:
            raise ValueError("Polygon area must be non-zero.")
        return self


class Geometry(ApiModel):
    """Polygon plus containing bounding box."""

    polygon: NormalisedPolygon
    bbox: NormalisedBoundingBox

    @model_validator(mode="after")
    def _bbox_contains_polygon(self) -> Geometry:
        left = self.bbox.x
        top = self.bbox.y
        right = self.bbox.x + self.bbox.width
        bottom = self.bbox.y + self.bbox.height
        for point in self.polygon.points:
            if (
                point.x < left - _BBOX_CONTAIN_TOLERANCE
                or point.x > right + _BBOX_CONTAIN_TOLERANCE
                or point.y < top - _BBOX_CONTAIN_TOLERANCE
                or point.y > bottom + _BBOX_CONTAIN_TOLERANCE
            ):
                raise ValueError("Bounding box must contain the polygon.")
        return self


def phase2_alignment_geometry() -> Geometry:
    """Return the fixed Phase 2 synthetic alignment-test geometry."""

    return Geometry(
        polygon=NormalisedPolygon(
            points=[
                NormalisedPoint(x=0.10, y=0.15),
                NormalisedPoint(x=0.35, y=0.15),
                NormalisedPoint(x=0.35, y=0.25),
                NormalisedPoint(x=0.10, y=0.25),
            ]
        ),
        bbox=NormalisedBoundingBox(x=0.10, y=0.15, width=0.25, height=0.10),
    )

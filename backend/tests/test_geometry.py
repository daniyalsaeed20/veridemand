from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.contracts.geometry import (
    Geometry,
    NormalisedBoundingBox,
    NormalisedPoint,
    NormalisedPolygon,
    phase2_alignment_geometry,
)
from backend.app.geometry.models import NormalisedPoint as GeoPoint
from backend.app.geometry.rotation import rotate_normalised_point
from backend.app.geometry.validation import clamp_bbox_to_page, validate_rotation_degrees


def test_normalised_point_accepts_unit_square() -> None:
    point = NormalisedPoint(x=0.0, y=1.0)
    assert point.x == 0.0
    assert point.y == 1.0


def test_normalised_point_rejects_out_of_range() -> None:
    with pytest.raises(ValidationError):
        NormalisedPoint(x=1.1, y=0.5)


def test_normalised_point_rejects_non_finite() -> None:
    with pytest.raises(ValidationError):
        NormalisedPoint(x=float("nan"), y=0.5)


def test_bbox_clamps_via_helper() -> None:
    bbox = NormalisedBoundingBox(x=0.95, y=0.0, width=0.05, height=0.5)
    clamped = clamp_bbox_to_page(bbox)
    assert clamped.x == pytest.approx(0.95)
    assert clamped.width == pytest.approx(0.05)


def test_bbox_rejects_crossing_page_boundary() -> None:
    with pytest.raises(ValidationError, match="boundary"):
        NormalisedBoundingBox(x=0.9, y=0.9, width=0.5, height=0.5)


def test_polygon_requires_non_zero_area() -> None:
    with pytest.raises(ValidationError, match="non-zero"):
        NormalisedPolygon(
            points=[
                NormalisedPoint(x=0.1, y=0.1),
                NormalisedPoint(x=0.5, y=0.1),
                NormalisedPoint(x=0.9, y=0.1),
            ]
        )


def test_geometry_requires_bbox_contains_polygon() -> None:
    with pytest.raises(ValidationError, match="contain"):
        Geometry(
            polygon=NormalisedPolygon(
                points=[
                    NormalisedPoint(x=0.1, y=0.1),
                    NormalisedPoint(x=0.5, y=0.1),
                    NormalisedPoint(x=0.5, y=0.5),
                ]
            ),
            bbox=NormalisedBoundingBox(x=0.2, y=0.2, width=0.1, height=0.1),
        )


def test_phase2_alignment_geometry_is_valid() -> None:
    geometry = phase2_alignment_geometry()
    assert geometry.bbox.width == pytest.approx(0.25)
    assert len(geometry.polygon.points) == 4


@pytest.mark.parametrize(
    ("rotation", "point", "expected"),
    [
        (0, GeoPoint(x=0.2, y=0.3), GeoPoint(x=0.2, y=0.3)),
        (90, GeoPoint(x=0.2, y=0.3), GeoPoint(x=0.7, y=0.2)),
        (180, GeoPoint(x=0.2, y=0.3), GeoPoint(x=0.8, y=0.7)),
        (270, GeoPoint(x=0.2, y=0.3), GeoPoint(x=0.3, y=0.8)),
    ],
)
def test_rotate_normalised_point(rotation: int, point: GeoPoint, expected: GeoPoint) -> None:
    rotated = rotate_normalised_point(point, rotation)
    assert rotated.x == pytest.approx(expected.x)
    assert rotated.y == pytest.approx(expected.y)


def test_validate_rotation_degrees_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="0, 90, 180, or 270"):
        validate_rotation_degrees(45)


def test_clamp_bbox_preserves_in_page_box() -> None:
    bbox = NormalisedBoundingBox(x=0.2, y=0.3, width=0.4, height=0.5)
    clamped = clamp_bbox_to_page(bbox)
    assert clamped.x == pytest.approx(0.2)
    assert clamped.width == pytest.approx(0.4)

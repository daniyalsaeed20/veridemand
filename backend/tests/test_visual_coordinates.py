"""Unit tests for OCR coordinate mapping."""

from __future__ import annotations

import pytest

from backend.app.extraction.visual.coordinates import map_pixel_polygon
from backend.app.extraction.visual.errors import VisualOcrError


def test_pixel_polygon_normalisation() -> None:
    mapped = map_pixel_polygon(
        [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)],
        width_pixels=200,
        height_pixels=100,
    )
    assert mapped.bbox.x == 0.0
    assert mapped.bbox.y == 0.0
    assert mapped.bbox.width == pytest.approx(0.5)
    assert mapped.bbox.height == pytest.approx(0.5)


def test_material_overflow_rejected() -> None:
    with pytest.raises(VisualOcrError):
        map_pixel_polygon(
            [(-50.0, 0.0), (100.0, 0.0), (100.0, 50.0), (-50.0, 50.0)],
            width_pixels=100,
            height_pixels=100,
        )


def test_zero_area_rejected() -> None:
    with pytest.raises(VisualOcrError):
        map_pixel_polygon(
            [(10.0, 10.0), (10.0, 10.0), (10.0, 10.0)],
            width_pixels=100,
            height_pixels=100,
        )

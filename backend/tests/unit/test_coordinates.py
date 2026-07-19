"""Unit tests for coordinate normalization and highlight mapping."""

from __future__ import annotations

import pytest

from app.services.extraction.coordinates import (
    PageGeometry,
    pdfplumber_bbox_to_normalized_quad,
    screen_rect_from_normalized,
)


def test_pdfplumber_bbox_normalizes_to_unit_square() -> None:
    geom = PageGeometry(width=100.0, height=200.0)
    quad = pdfplumber_bbox_to_normalized_quad(10, 20, 30, 40, geom)
    assert quad is not None
    assert quad[0] == pytest.approx([0.1, 0.1])
    assert quad[1] == pytest.approx([0.3, 0.1])
    assert quad[2] == pytest.approx([0.3, 0.2])
    assert quad[3] == pytest.approx([0.1, 0.2])


def test_out_of_bounds_geometry_rejected() -> None:
    geom = PageGeometry(width=100.0, height=100.0)
    # Far outside page — should reject rather than silent wrong highlight
    quad = pdfplumber_bbox_to_normalized_quad(-50, -50, -10, -10, geom)
    assert quad is None


def test_rotation_90_maps_corners() -> None:
    geom = PageGeometry(width=100.0, height=100.0, rotation=90)
    quad = pdfplumber_bbox_to_normalized_quad(0, 0, 50, 50, geom)
    assert quad is not None
    # (0,0) -> (0,1); (0.5,0) -> (0,0.5); (0.5,0.5) -> (0.5,0.5); (0,0.5) -> (0.5,1)
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    assert min(xs) == pytest.approx(0.0)
    assert max(xs) == pytest.approx(0.5)
    assert min(ys) == pytest.approx(0.5)
    assert max(ys) == pytest.approx(1.0)


def test_screen_rect_scales_with_render_size() -> None:
    polygon = [[0.1, 0.2], [0.3, 0.2], [0.3, 0.4], [0.1, 0.4]]
    x, y, w, h = screen_rect_from_normalized(polygon, rendered_width=1000, rendered_height=2000)
    assert (x, y, w, h) == pytest.approx((100.0, 400.0, 200.0, 400.0))
    x2, y2, w2, h2 = screen_rect_from_normalized(polygon, rendered_width=500, rendered_height=1000)
    assert (x2, y2, w2, h2) == pytest.approx((50.0, 200.0, 100.0, 200.0))

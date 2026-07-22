"""Unit tests for visual DPI and render limit helpers."""

from __future__ import annotations

import pytest

from backend.app.contracts.errors import ErrorCode
from backend.app.extraction.visual.errors import VisualOcrError
from backend.app.extraction.visual.renderer import compute_effective_dpi


def test_dpi_to_scale_within_limits() -> None:
    dpi = compute_effective_dpi(
        page_width_points=612,
        page_height_points=792,
        target_dpi=200,
        min_effective_dpi=120,
        max_render_pixels=40_000_000,
        max_render_side_pixels=6000,
    )
    assert dpi == 200.0


def test_pixel_limit_downscales_dpi() -> None:
    dpi = compute_effective_dpi(
        page_width_points=612,
        page_height_points=792,
        target_dpi=600,
        min_effective_dpi=72,
        max_render_pixels=500_000,
        max_render_side_pixels=6000,
    )
    assert 72 <= dpi < 600


def test_minimum_dpi_failure() -> None:
    with pytest.raises(VisualOcrError) as exc:
        compute_effective_dpi(
            page_width_points=10_000,
            page_height_points=10_000,
            target_dpi=200,
            min_effective_dpi=120,
            max_render_pixels=1000,
            max_render_side_pixels=50,
        )
    assert exc.value.code is ErrorCode.VISUAL_PAGE_RESOURCE_LIMIT

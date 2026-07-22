"""Unit tests for PaddleOCR schema adapter helpers (no real Paddle required)."""

from __future__ import annotations

from backend.app.extraction.visual.paddle_adapter import (
    _clamp01,
    _first_result_dict,
    _looks_cjk_without_whitespace,
    _to_polygon,
)


def test_clamp01() -> None:
    assert _clamp01(-1.0) == 0.0
    assert _clamp01(0.5) == 0.5
    assert _clamp01(2.0) == 1.0


def test_first_result_dict_from_list() -> None:
    payload = [{"rec_texts": ["a"], "dt_polys": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}]
    assert _first_result_dict(payload) == payload[0]


def test_to_polygon_quad() -> None:
    poly = _to_polygon([[0, 0], [10, 0], [10, 5], [0, 5]])
    assert poly == [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)]


def test_cjk_without_whitespace_heuristic() -> None:
    assert _looks_cjk_without_whitespace("汉字测试") is True
    assert _looks_cjk_without_whitespace("hello world") is False

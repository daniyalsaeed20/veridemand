"""Unit tests for native usability routing (no OCR invoked)."""

from __future__ import annotations

from app.models.app_settings import AppSettings
from app.models.enums import PageRoute
from app.services.extraction.routing import (
    NativeWord,
    score_native_text_usability,
    select_page_route,
)


def _word(text: str, x0: float, top: float, x1: float, bottom: float) -> NativeWord:
    return NativeWord(
        text=text,
        x0=x0,
        top=top,
        x1=x1,
        bottom=bottom,
        width=x1 - x0,
        height=bottom - top,
    )


def test_empty_page_routes_manual_review() -> None:
    settings = AppSettings()
    diag = score_native_text_usability([], page_width=612, page_height=792, settings=settings)
    assert diag.is_blank
    assert select_page_route(diag, settings) == PageRoute.MANUAL_REVIEW


def test_sparse_text_routes_ocr_without_running_ocr() -> None:
    settings = AppSettings()
    words = [_word("hi", 10, 10, 20, 20)]
    diag = score_native_text_usability(words, page_width=612, page_height=792, settings=settings)
    assert select_page_route(diag, settings) == PageRoute.OCR


def test_rich_native_text_routes_native() -> None:
    settings = AppSettings()
    words = [_word(f"word{i:02d}", 10 + i * 40, 50, 40 + i * 40, 70) for i in range(20)]
    diag = score_native_text_usability(words, page_width=612, page_height=792, settings=settings)
    assert select_page_route(diag, settings) == PageRoute.NATIVE


def test_broken_encoding_routes_ocr() -> None:
    settings = AppSettings()
    words = [_word("\ufffd" * 50, 10, 10, 400, 40) for _ in range(5)]
    diag = score_native_text_usability(words, page_width=612, page_height=792, settings=settings)
    assert select_page_route(diag, settings) == PageRoute.OCR
    assert "broken_text_layer" in diag.quality_flags

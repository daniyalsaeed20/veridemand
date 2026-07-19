"""Native usability gate regression (B-02) — synthetic words; no PaddleOCR; no firm PII."""

from __future__ import annotations

import ast
from pathlib import Path

from app.models.app_settings import AppSettings
from app.models.enums import PageRoute
from app.services.extraction.routing import (
    NativeWord,
    score_native_text_usability,
    select_page_route,
)


def _w(
    text: str,
    x0: float,
    top: float,
    x1: float | None = None,
    bottom: float | None = None,
) -> NativeWord:
    # Generous boxes so synthetic prose clears native_min_text_coverage without
    # tripping oversized-box heuristics.
    x1 = x0 + max(36.0, len(text) * 7.0) if x1 is None else x1
    bottom = top + 18.0 if bottom is None else bottom
    return NativeWord(
        text=text,
        x0=x0,
        top=top,
        x1=x1,
        bottom=bottom,
        width=x1 - x0,
        height=bottom - top,
    )


def _route(
    words: list[NativeWord], settings: AppSettings | None = None
) -> tuple[PageRoute, object]:
    settings = settings or AppSettings()
    diag = score_native_text_usability(words, page_width=612, page_height=792, settings=settings)
    return select_page_route(diag, settings), diag


def test_pathological_missing_space_routes_ocr() -> None:
    words = [
        _w("thismissingspacephraseispathologicallylong" + str(i), 10, 20 + i * 14)
        for i in range(25)
    ]
    route, diag = _route(words)
    assert route == PageRoute.OCR
    assert diag.pathological_tokenization
    assert "pathological_tokenization" in diag.quality_flags


def test_cid_like_corrupted_extraction_routes_ocr() -> None:
    words = [_w(f"(cid:{100 + i})garbage", 10, 20 + i * 14) for i in range(20)]
    words.extend([_w(f"word{i:02d}", 200, 20 + i * 14) for i in range(20)])
    route, diag = _route(words)
    assert route == PageRoute.OCR
    assert "broken_text_layer" in diag.quality_flags or diag.cid_marker_ratio > 0


def test_extremely_long_malformed_tokens_routes_ocr() -> None:
    words = [_w("X" * 120 + str(i), 10, 20 + i * 14) for i in range(30)]
    route, diag = _route(words)
    assert route == PageRoute.OCR
    assert diag.pathological_tokenization
    assert diag.max_token_length >= 120


def test_normal_prose_remains_native() -> None:
    sentence = (
        "The patient reported neck pain after the motor vehicle collision on Main Street "
        "and followed up with physical therapy as recommended by the treating physician "
        "who documented restricted range of motion and prescribed continued care"
    ).split()
    words = [_w(tok, 20 + (i % 6) * 90, 40 + (i // 6) * 22) for i, tok in enumerate(sentence)]
    route, diag = _route(words)
    assert diag.text_coverage >= 0.02
    assert route == PageRoute.NATIVE
    assert not diag.pathological_tokenization


def test_dense_table_remains_usable() -> None:
    words: list[NativeWord] = []
    for row in range(10):
        for col in range(8):
            words.append(_w(f"c{row}{col}", 20 + col * 70, 40 + row * 22))
    route, diag = _route(words)
    assert diag.text_coverage >= 0.02
    assert route == PageRoute.NATIVE
    assert not diag.pathological_tokenization


def test_single_long_url_does_not_reject() -> None:
    words = [
        _w("Visit", 20, 40),
        _w("https://example.com/very/long/path/to/resource?id=12345&ref=abcdef", 80, 40, x1=400),
        _w("for", 20, 70),
        _w("details", 60, 70),
        _w("about", 130, 70),
        _w("the", 190, 70),
        _w("claim", 240, 70),
        _w("number", 300, 70),
        _w("and", 380, 70),
        _w("related", 430, 70),
        _w("medical", 20, 100),
        _w("billing", 100, 100),
        _w("records", 180, 100),
        _w("submitted", 280, 100),
        _w("with", 380, 100),
        _w("this", 440, 100),
        _w("demand", 20, 130),
        _w("package", 100, 130),
        _w("today", 200, 130),
        _w("please", 280, 130),
        _w("review", 360, 130),
        _w("carefully", 440, 130),
        _w("before", 20, 160),
        _w("responding", 100, 160),
    ]
    route, diag = _route(words)
    assert route == PageRoute.NATIVE
    assert not diag.pathological_tokenization
    assert diag.max_token_length > 40


def test_long_identifier_alone_does_not_reject() -> None:
    words = [_w(f"word{i:02d}", 20 + (i % 5) * 100, 40 + (i // 5) * 22) for i in range(24)]
    words.insert(3, _w("CLAIMID-2026-ABCDEFGH-99999-ZZZZ", 20, 300, x1=280))
    route, diag = _route(words)
    assert route == PageRoute.NATIVE
    assert not diag.pathological_tokenization


def test_mixed_long_and_normal_tokens_remain_native() -> None:
    words = [_w(f"normal{i}", 20, 20 + i * 20) for i in range(20)]
    words.append(_w("https://files.example.org/a/b/c/d/e/document.pdf", 20, 440, x1=360))
    words.append(_w("REF-IDENTIFIER-LONG-BUT-SINGLE", 20, 470, x1=300))
    route, diag = _route(words)
    assert route == PageRoute.NATIVE


def test_blank_page_manual_review() -> None:
    route, diag = _route([])
    assert route == PageRoute.MANUAL_REVIEW
    assert diag.is_blank
    assert not diag.pathological_tokenization


def test_scanned_image_only_routes_ocr() -> None:
    settings = AppSettings()
    diag = score_native_text_usability(
        [_w("x", 10, 10, 12, 12)],
        page_width=612,
        page_height=792,
        image_coverage=0.85,
        settings=settings,
    )
    assert select_page_route(diag, settings) == PageRoute.OCR


def test_pathological_does_not_publish_as_native() -> None:
    settings = AppSettings()
    words = [
        _w("thismissingspacephraseispathologicallylong" + str(i), 10, 20 + i * 14)
        for i in range(25)
    ]
    diag = score_native_text_usability(words, page_width=612, page_height=792, settings=settings)
    assert select_page_route(diag, settings) == PageRoute.OCR
    assert diag.pathological_tokenization
    # native.py publishes tokens only for PageRoute.NATIVE
    assert "awaiting_ocr" not in diag.quality_flags  # added at extract time for OCR route


def test_no_paddleocr_on_extraction_package() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "services" / "extraction"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "paddle" not in alias.name.lower()
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "paddle" not in node.module.lower()

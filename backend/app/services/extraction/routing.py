"""Native text usability scoring and page routing (Phase 2; OCR deferred)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.app_settings import AppSettings
from app.models.enums import PageRoute


@dataclass
class NativeWord:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    width: float
    height: float


@dataclass
class PageDiagnostics:
    char_count: int = 0
    word_count: int = 0
    text_coverage: float = 0.0
    image_coverage: float = 0.0
    replacement_ratio: float = 0.0
    zero_width_or_overlap_ratio: float = 0.0
    reading_order_score: float = 1.0
    is_blank: bool = False
    quality_flags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def score_native_text_usability(
    words: list[NativeWord],
    *,
    page_width: float,
    page_height: float,
    image_coverage: float = 0.0,
    settings: AppSettings,
) -> PageDiagnostics:
    page_area = max(page_width * page_height, 1.0)
    diagnostics = PageDiagnostics(image_coverage=image_coverage)

    if not words:
        diagnostics.is_blank = True
        diagnostics.quality_flags.append("blank")
        return diagnostics

    texts = [w.text or "" for w in words]
    joined = "".join(texts)
    diagnostics.char_count = len(joined)
    diagnostics.word_count = sum(1 for t in texts if t.strip())

    glyph_area = 0.0
    zero_or_overlap = 0
    replacement = 0
    for word in words:
        w = max(0.0, word.x1 - word.x0)
        h = max(0.0, word.bottom - word.top)
        glyph_area += w * h
        if w <= 0.5 or h <= 0.5:
            zero_or_overlap += 1
        replacement += word.text.count("\ufffd") + sum(
            1 for ch in word.text if ord(ch) < 32 and ch not in "\t\n\r"
        )

    diagnostics.text_coverage = min(1.0, glyph_area / page_area)
    n = max(len(words), 1)
    diagnostics.zero_width_or_overlap_ratio = zero_or_overlap / n
    diagnostics.replacement_ratio = replacement / max(diagnostics.char_count, 1)
    diagnostics.reading_order_score = _reading_order_score(words)

    if diagnostics.char_count == 0:
        diagnostics.is_blank = True
        diagnostics.quality_flags.append("blank")
    if diagnostics.replacement_ratio > settings.native_max_replacement_ratio:
        diagnostics.quality_flags.append("broken_text_layer")
        diagnostics.warnings.append("high_replacement_ratio")
    if diagnostics.zero_width_or_overlap_ratio > settings.native_max_zero_width_or_overlap_ratio:
        diagnostics.quality_flags.append("broken_text_layer")
        diagnostics.warnings.append("bad_geometry")
    if diagnostics.reading_order_score < settings.native_min_reading_order_score:
        diagnostics.warnings.append("poor_reading_order")

    return diagnostics


def select_page_route(diagnostics: PageDiagnostics, settings: AppSettings) -> PageRoute:
    """Provisional native→OCR routing. Phase 2 never runs OCR; it only sets the route."""
    if diagnostics.is_blank or "blank" in diagnostics.quality_flags:
        return PageRoute.MANUAL_REVIEW

    if (
        diagnostics.replacement_ratio > settings.native_max_replacement_ratio
        or diagnostics.zero_width_or_overlap_ratio > settings.native_max_zero_width_or_overlap_ratio
    ):
        return PageRoute.OCR

    if (
        diagnostics.char_count < settings.native_min_chars
        or diagnostics.text_coverage < settings.native_min_text_coverage
    ):
        return PageRoute.OCR

    if diagnostics.reading_order_score < settings.native_min_reading_order_score:
        return PageRoute.OCR

    if (
        diagnostics.image_coverage >= settings.native_likely_scan_image_coverage
        and diagnostics.text_coverage < settings.native_min_text_coverage
    ):
        return PageRoute.OCR

    return PageRoute.NATIVE


def _reading_order_score(words: list[NativeWord]) -> float:
    """Heuristic: fraction of consecutive pairs that advance left-to-right / top-to-bottom."""
    if len(words) < 2:
        return 1.0
    good = 0
    total = 0
    for prev, cur in zip(words, words[1:], strict=False):
        total += 1
        same_line = abs(prev.top - cur.top) <= max(prev.height, cur.height, 1.0) * 0.6
        if same_line and cur.x0 >= prev.x0 - 1.0:
            good += 1
        elif not same_line and cur.top >= prev.top - 1.0:
            good += 1
    return good / max(total, 1)

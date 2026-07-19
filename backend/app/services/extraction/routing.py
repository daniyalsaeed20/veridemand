"""Native text usability scoring and page routing (Phase 2; OCR deferred).

Hardening B-02: multi-signal pathological tokenization gate before usable
SourceTokens/SourceSpans are committed. Phase 2 never runs OCR.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from app.models.app_settings import AppSettings
from app.models.enums import PageRoute

_CID_MARKER_RE = re.compile(r"\(cid:\d+\)", re.IGNORECASE)
_REPEATED_GLYPH_RE = re.compile(r"(.)\1{8,}")


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
    control_char_ratio: float = 0.0
    printable_ratio: float = 1.0
    zero_width_or_overlap_ratio: float = 0.0
    oversized_box_ratio: float = 0.0
    reading_order_score: float = 1.0
    mean_token_length: float = 0.0
    median_token_length: float = 0.0
    max_token_length: int = 0
    long_token_ratio: float = 0.0
    cid_marker_ratio: float = 0.0
    repeated_glyph_ratio: float = 0.0
    private_use_ratio: float = 0.0
    is_blank: bool = False
    pathological_tokenization: bool = False
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
    lengths = [len(t) for t in texts]
    joined = "".join(texts)
    diagnostics.char_count = len(joined)
    diagnostics.word_count = sum(1 for t in texts if t.strip())
    diagnostics.mean_token_length = float(statistics.fmean(lengths)) if lengths else 0.0
    diagnostics.median_token_length = float(statistics.median(lengths)) if lengths else 0.0
    diagnostics.max_token_length = max(lengths) if lengths else 0
    band = settings.native_long_token_band
    diagnostics.long_token_ratio = sum(1 for n in lengths if n > band) / max(len(lengths), 1)

    glyph_area = 0.0
    zero_or_overlap = 0
    oversized = 0
    replacement = 0
    control = 0
    printable = 0
    cid_hits = 0
    repeated = 0
    private_use = 0

    for word in words:
        w = max(0.0, word.x1 - word.x0)
        h = max(0.0, word.bottom - word.top)
        glyph_area += w * h
        if w <= 0.5 or h <= 0.5:
            zero_or_overlap += 1
        # Abnormally large token box vs page
        if (w * h) / page_area >= 0.25:
            oversized += 1
        text = word.text or ""
        replacement += text.count("\ufffd")
        for ch in text:
            o = ord(ch)
            if o < 32 and ch not in "\t\n\r":
                control += 1
            elif ch.isprintable() or ch in "\t\n\r":
                printable += 1
            if 0xE000 <= o <= 0xF8FF:
                private_use += 1
        if _CID_MARKER_RE.search(text):
            cid_hits += 1
        if _REPEATED_GLYPH_RE.search(text):
            repeated += 1

    n = max(len(words), 1)
    char_n = max(diagnostics.char_count, 1)
    diagnostics.text_coverage = min(1.0, glyph_area / page_area)
    diagnostics.zero_width_or_overlap_ratio = zero_or_overlap / n
    diagnostics.oversized_box_ratio = oversized / n
    diagnostics.replacement_ratio = replacement / char_n
    diagnostics.control_char_ratio = control / char_n
    diagnostics.printable_ratio = printable / char_n
    diagnostics.cid_marker_ratio = cid_hits / n
    diagnostics.repeated_glyph_ratio = repeated / n
    diagnostics.private_use_ratio = private_use / char_n
    diagnostics.reading_order_score = _reading_order_score(words)

    if diagnostics.char_count == 0:
        diagnostics.is_blank = True
        diagnostics.quality_flags.append("blank")
        return diagnostics

    _apply_quality_flags(diagnostics, settings)
    return diagnostics


def _apply_quality_flags(diagnostics: PageDiagnostics, settings: AppSettings) -> None:
    if diagnostics.replacement_ratio > settings.native_max_replacement_ratio:
        diagnostics.quality_flags.append("broken_text_layer")
        diagnostics.warnings.append("high_replacement_ratio")
    if diagnostics.control_char_ratio > settings.native_max_control_char_ratio:
        diagnostics.quality_flags.append("broken_text_layer")
        diagnostics.warnings.append("high_control_char_ratio")
    if diagnostics.printable_ratio < settings.native_min_printable_ratio:
        diagnostics.quality_flags.append("broken_text_layer")
        diagnostics.warnings.append("low_printable_ratio")
    if diagnostics.zero_width_or_overlap_ratio > settings.native_max_zero_width_or_overlap_ratio:
        diagnostics.quality_flags.append("broken_text_layer")
        diagnostics.warnings.append("bad_geometry")
    if diagnostics.oversized_box_ratio > settings.native_max_oversized_box_ratio:
        diagnostics.quality_flags.append("broken_text_layer")
        diagnostics.warnings.append("oversized_token_boxes")
    if diagnostics.cid_marker_ratio > 0.05 or diagnostics.private_use_ratio > 0.05:
        diagnostics.quality_flags.append("broken_text_layer")
        diagnostics.warnings.append("cid_or_private_use_glyphs")
    if diagnostics.repeated_glyph_ratio > 0.15:
        diagnostics.quality_flags.append("broken_text_layer")
        diagnostics.warnings.append("repeated_glyph_anomaly")
    if diagnostics.reading_order_score < settings.native_min_reading_order_score:
        diagnostics.warnings.append("poor_reading_order")

    # Multi-signal pathological tokenization (not max-length alone).
    long_and_elevated = diagnostics.long_token_ratio > settings.native_max_long_token_ratio and (
        diagnostics.mean_token_length > settings.native_max_mean_token_length
        or diagnostics.median_token_length > settings.native_max_median_token_length
    )
    # Dual elevation: missing-space pages raise both mean and median without a single URL.
    dual_elevated = (
        diagnostics.mean_token_length > settings.native_max_mean_token_length
        and diagnostics.median_token_length > settings.native_max_median_token_length
    )
    if long_and_elevated or dual_elevated:
        diagnostics.pathological_tokenization = True
        diagnostics.quality_flags.append("pathological_tokenization")
        diagnostics.quality_flags.append("broken_text_layer")
        diagnostics.warnings.append("pathological_tokenization")


def select_page_route(diagnostics: PageDiagnostics, settings: AppSettings) -> PageRoute:
    """Provisional native→OCR routing. Phase 2 never runs OCR; it only sets the route."""
    if diagnostics.is_blank or "blank" in diagnostics.quality_flags:
        return PageRoute.MANUAL_REVIEW

    if (
        diagnostics.pathological_tokenization
        or "pathological_tokenization" in diagnostics.quality_flags
    ):
        return PageRoute.OCR

    if (
        diagnostics.replacement_ratio > settings.native_max_replacement_ratio
        or diagnostics.control_char_ratio > settings.native_max_control_char_ratio
        or diagnostics.printable_ratio < settings.native_min_printable_ratio
        or diagnostics.zero_width_or_overlap_ratio > settings.native_max_zero_width_or_overlap_ratio
        or diagnostics.oversized_box_ratio > settings.native_max_oversized_box_ratio
        or diagnostics.cid_marker_ratio > 0.05
        or diagnostics.private_use_ratio > 0.05
        or "broken_text_layer" in diagnostics.quality_flags
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

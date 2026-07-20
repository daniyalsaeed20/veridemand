"""Deterministic OCR page-quality assessment (FR-EXT-07) including under-detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.models.app_settings import AppSettings
from app.models.enums import IssueSeverity
from app.models.source_token import SourceToken


class OcrPageOutcome(StrEnum):
    USABLE = "ocr_usable"
    USABLE_WITH_WARNING = "ocr_usable_with_warning"
    LOW_CONFIDENCE = "ocr_low_confidence"
    FAILED = "ocr_failed"
    BLANK = "blank"


@dataclass(frozen=True)
class PageInkContext:
    """Render-time ink/density signals (not inventable from tokens alone)."""

    dark_pixel_fraction: float
    width: int
    height: int
    megapixels: float


@dataclass
class OcrQualityAssessment:
    outcome: OcrPageOutcome
    quality_flags: list[str] = field(default_factory=list)
    mean_confidence: float | None = None
    printable_ratio: float = 1.0
    control_char_ratio: float = 0.0
    coverage: float = 0.0
    overlap_ratio: float = 0.0
    duplicate_ratio: float = 0.0
    dark_pixel_fraction: float | None = None
    under_detection: bool = False
    issue_type: str | None = None
    issue_severity: IssueSeverity | None = None
    issue_title: str | None = None
    warnings: list[str] = field(default_factory=list)


def assess_ocr_tokens(
    tokens: list[SourceToken],
    *,
    settings: AppSettings,
    engine_warnings: list[str] | None = None,
    ink: PageInkContext | None = None,
) -> OcrQualityAssessment:
    warnings = list(engine_warnings or [])
    if not tokens:
        return OcrQualityAssessment(
            outcome=OcrPageOutcome.BLANK,
            quality_flags=["blank"],
            dark_pixel_fraction=ink.dark_pixel_fraction if ink else None,
            issue_type="extraction.unreadable_page",
            issue_severity=IssueSeverity.RED,
            issue_title="Page has no readable OCR text",
            warnings=warnings + ["ocr_no_tokens"],
        )

    confidences = [t.confidence for t in tokens]
    mean_conf = sum(confidences) / len(confidences)
    joined = "".join(t.text for t in tokens)
    control = 0
    printable = 0
    for ch in joined:
        o = ord(ch)
        if o < 32 and ch not in "\t\n\r":
            control += 1
        elif ch.isprintable() or ch in "\t\n\r":
            printable += 1
    char_n = max(len(joined), 1)
    printable_ratio = printable / char_n
    control_ratio = control / char_n

    coverage = _token_coverage(tokens)
    overlap_ratio = _overlap_ratio(tokens)
    duplicate_ratio = _duplicate_ratio(tokens)
    band_concentration = _band_concentration(tokens)

    flags: list[str] = []
    if overlap_ratio > 0.35:
        flags.append("duplicate_detections")
        warnings.append("high_overlap_detections")
    if duplicate_ratio > 0.25:
        flags.append("duplicate_page")
        warnings.append("duplicate_text_detections")
    if printable_ratio < 0.85 or control_ratio > 0.05:
        flags.append("low_confidence")
        warnings.append("ocr_garbage_characters")

    if any(_looks_critical(t.text) and t.confidence < 0.70 for t in tokens):
        warnings.append("low_conf_critical_looking_string")
        if "low_confidence" not in flags:
            flags.append("low_confidence")

    under = False
    dark = ink.dark_pixel_fraction if ink is not None else None
    if ink is not None:
        under = _is_under_detected(
            tokens=tokens,
            coverage=coverage,
            dark_pixel_fraction=ink.dark_pixel_fraction,
            band_concentration=band_concentration,
            settings=settings,
        )
        if under:
            flags.append("insufficient_coverage")
            warnings.append("ocr_under_detection")

    flags = list(dict.fromkeys(flags))

    # Under-detection after assessment: not usable (B-03)
    if under:
        return OcrQualityAssessment(
            outcome=OcrPageOutcome.FAILED,
            quality_flags=flags,
            mean_confidence=mean_conf,
            printable_ratio=printable_ratio,
            control_char_ratio=control_ratio,
            coverage=coverage,
            overlap_ratio=overlap_ratio,
            duplicate_ratio=duplicate_ratio,
            dark_pixel_fraction=dark,
            under_detection=True,
            issue_type="extraction.insufficient_ocr_coverage",
            issue_severity=IssueSeverity.AMBER,
            issue_title="OCR detected too little text for a visually dense page",
            warnings=warnings,
        )

    if mean_conf < settings.ocr_page_mean_conf_low or printable_ratio < 0.80:
        flags.append("low_confidence")
        return OcrQualityAssessment(
            outcome=OcrPageOutcome.LOW_CONFIDENCE,
            quality_flags=list(dict.fromkeys(flags)),
            mean_confidence=mean_conf,
            printable_ratio=printable_ratio,
            control_char_ratio=control_ratio,
            coverage=coverage,
            overlap_ratio=overlap_ratio,
            duplicate_ratio=duplicate_ratio,
            dark_pixel_fraction=dark,
            issue_type="extraction.low_ocr_confidence",
            issue_severity=IssueSeverity.AMBER,
            issue_title="OCR confidence is too low for reliable downstream use",
            warnings=warnings,
        )

    if mean_conf < settings.ocr_page_mean_conf_retry_trigger or flags:
        if "low_confidence" not in flags and mean_conf < settings.ocr_page_mean_conf_retry_trigger:
            flags.append("low_confidence")
        return OcrQualityAssessment(
            outcome=OcrPageOutcome.USABLE_WITH_WARNING,
            quality_flags=list(dict.fromkeys(flags)),
            mean_confidence=mean_conf,
            printable_ratio=printable_ratio,
            control_char_ratio=control_ratio,
            coverage=coverage,
            overlap_ratio=overlap_ratio,
            duplicate_ratio=duplicate_ratio,
            dark_pixel_fraction=dark,
            issue_type="extraction.low_ocr_confidence" if flags else None,
            issue_severity=IssueSeverity.AMBER if flags else None,
            issue_title="OCR completed with warnings" if flags else None,
            warnings=warnings,
        )

    return OcrQualityAssessment(
        outcome=OcrPageOutcome.USABLE,
        quality_flags=[],
        mean_confidence=mean_conf,
        printable_ratio=printable_ratio,
        control_char_ratio=control_ratio,
        coverage=coverage,
        overlap_ratio=overlap_ratio,
        duplicate_ratio=duplicate_ratio,
        dark_pixel_fraction=dark,
        warnings=warnings,
    )


def score_pass_for_retry_choice(
    tokens: list[SourceToken],
    *,
    settings: AppSettings,
    ink: PageInkContext | None = None,
) -> float:
    """Higher is better — coverage/completeness can beat mean-confidence alone."""
    assessment = assess_ocr_tokens(tokens, settings=settings, ink=ink)
    if assessment.outcome == OcrPageOutcome.BLANK:
        return -1.0
    if assessment.under_detection:
        # Severely penalize under-detected passes so denser retries win
        mean = assessment.mean_confidence or 0.0
        return mean * 20.0 + assessment.coverage * 80.0 + min(len(tokens), 400) * 0.25 - 50.0
    mean = assessment.mean_confidence or 0.0
    return (
        mean * 40.0
        + assessment.printable_ratio * 20.0
        + min(len(tokens), 400) * 0.2
        + assessment.coverage * 60.0
        - assessment.overlap_ratio * 15.0
        - assessment.control_char_ratio * 30.0
    )


def _is_under_detected(
    *,
    tokens: list[SourceToken],
    coverage: float,
    dark_pixel_fraction: float,
    band_concentration: float,
    settings: AppSettings,
) -> bool:
    """Multi-signal gate: dark pixels alone never fail a page."""
    ink_rich = dark_pixel_fraction >= settings.ocr_min_ink_for_coverage_check
    if not ink_rich:
        return False

    signals = 0
    if coverage < settings.ocr_min_token_coverage:
        signals += 1
    if len(tokens) < settings.ocr_min_tokens_ink_rich:
        signals += 1
    ratio = coverage / max(dark_pixel_fraction, 1e-6)
    if ratio < settings.ocr_min_coverage_to_ink_ratio:
        signals += 1
    # Most detections in one vertical third while ink is page-wide
    if band_concentration >= 0.85 and dark_pixel_fraction >= 0.12:
        signals += 1
    return signals >= 2


def _band_concentration(tokens: list[SourceToken]) -> float:
    """Fraction of tokens in the densest vertical third (top/mid/bot)."""
    if not tokens:
        return 0.0
    bands = [0, 0, 0]
    for token in tokens:
        y = sum(p[1] for p in token.polygon) / max(len(token.polygon), 1)
        if y < 0.33:
            bands[0] += 1
        elif y < 0.66:
            bands[1] += 1
        else:
            bands[2] += 1
    return max(bands) / max(len(tokens), 1)


def _token_coverage(tokens: list[SourceToken]) -> float:
    area = 0.0
    for token in tokens:
        xs = [p[0] for p in token.polygon]
        ys = [p[1] for p in token.polygon]
        area += max(0.0, max(xs) - min(xs)) * max(0.0, max(ys) - min(ys))
    return min(1.0, area)


def _overlap_ratio(tokens: list[SourceToken]) -> float:
    if len(tokens) < 2:
        return 0.0
    overlaps = 0
    pairs = 0
    for i, a in enumerate(tokens):
        ab = _bbox(a.polygon)
        for b in tokens[i + 1 : i + 8]:
            pairs += 1
            if _iou(ab, _bbox(b.polygon)) > 0.5:
                overlaps += 1
    return overlaps / max(pairs, 1)


def _duplicate_ratio(tokens: list[SourceToken]) -> float:
    if not tokens:
        return 0.0
    seen: dict[str, int] = {}
    for t in tokens:
        key = t.text.strip().lower()
        if not key:
            continue
        seen[key] = seen.get(key, 0) + 1
    dupes = sum(c - 1 for c in seen.values() if c > 1)
    return dupes / max(len(tokens), 1)


def _bbox(polygon: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _iou(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _looks_critical(text: str) -> bool:
    import re

    patterns = [
        re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
        re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
        re.compile(r"\$\s?\d[\d,]*\.?\d*"),
        re.compile(r"\bclaim\b|\bpolicy\b|\bdol\b|\bdoi\b", re.I),
    ]
    return any(p.search(text) for p in patterns)


def measure_dark_pixel_fraction(image: object, *, threshold: int = 200) -> float:
    """Fraction of pixels darker than threshold (top-left grayscale)."""
    import numpy as np
    from PIL import Image as PILImage

    if not isinstance(image, PILImage.Image):
        return 0.0
    arr = np.asarray(image.convert("L"))
    if arr.size == 0:
        return 0.0
    return float((arr < threshold).mean())

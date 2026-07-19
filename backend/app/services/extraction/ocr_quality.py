"""Deterministic OCR page-quality assessment (FR-EXT-07)."""

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
    issue_type: str | None = None
    issue_severity: IssueSeverity | None = None
    issue_title: str | None = None
    warnings: list[str] = field(default_factory=list)


def assess_ocr_tokens(
    tokens: list[SourceToken],
    *,
    settings: AppSettings,
    engine_warnings: list[str] | None = None,
) -> OcrQualityAssessment:
    warnings = list(engine_warnings or [])
    if not tokens:
        return OcrQualityAssessment(
            outcome=OcrPageOutcome.BLANK,
            quality_flags=["blank"],
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

    # Critical-format warning signal only (not fact extraction)
    if any(_looks_critical(t.text) and t.confidence < 0.70 for t in tokens):
        warnings.append("low_conf_critical_looking_string")
        if "low_confidence" not in flags:
            flags.append("low_confidence")

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
        warnings=warnings,
    )


def score_pass_for_retry_choice(
    tokens: list[SourceToken],
    *,
    settings: AppSettings,
) -> float:
    """Higher is better — deterministic comparator for first vs retry pass."""
    assessment = assess_ocr_tokens(tokens, settings=settings)
    if assessment.outcome == OcrPageOutcome.BLANK:
        return -1.0
    mean = assessment.mean_confidence or 0.0
    return (
        mean * 100.0
        + assessment.printable_ratio * 20.0
        + min(len(tokens), 200) * 0.05
        + assessment.coverage * 10.0
        - assessment.overlap_ratio * 15.0
        - assessment.control_char_ratio * 30.0
    )


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

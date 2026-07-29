"""Printed OCR quality evidence, primary-pass gate, and pass selection.

Every displayed quality / fallback decision must derive from PrintedOcrQualityEvidence.
Mean confidence is never treated as transcript accuracy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.app.contracts.ocr import (
    QUALITY_POLICY_VERSION,
    ConfidenceDistribution,
    OcrPassComparison,
    OcrPassKind,
    OcrQualityStatus,
    PageProcessingProfile,
    PreprocessingVariant,
    PrintedOcrQualityEvidence,
)
from backend.app.extraction.visual.grid import GridInterferenceResult
from backend.app.extraction.visual.page_profile import PageProfileResult

_SYMBOL_RE = re.compile(r"^[\W_]+$", re.UNICODE)
_NUMERIC_RE = re.compile(r"^\d{1,4}$")


@dataclass(frozen=True, slots=True)
class QualityGateThresholds:
    """Profile-calibrated primary-pass acceptance thresholds."""

    max_low_confidence_ratio: float
    max_fragmentation: float
    max_single_char_token_ratio: float
    max_symbol_only_token_ratio: float
    max_over_segmentation: float
    min_text_coverage: float
    max_grid_intersection_ratio: float
    max_near_duplicate_ratio: float
    max_box_overlap_ratio: float
    min_geometry_valid_ratio: float
    min_median_words_per_line: float
    max_median_words_per_line: float
    # Sparse pages: do not require coverage above this absolute floor when sparse.
    sparse_min_lines: int = 0


def thresholds_for_profile(profile: PageProcessingProfile) -> QualityGateThresholds:
    if profile is PageProcessingProfile.DENSE_FORM:
        return QualityGateThresholds(
            max_low_confidence_ratio=0.35,
            max_fragmentation=0.42,
            max_single_char_token_ratio=0.28,
            max_symbol_only_token_ratio=0.18,
            max_over_segmentation=0.45,
            min_text_coverage=0.04,
            max_grid_intersection_ratio=0.55,
            max_near_duplicate_ratio=0.22,
            max_box_overlap_ratio=0.35,
            min_geometry_valid_ratio=0.92,
            min_median_words_per_line=0.0,
            max_median_words_per_line=14.0,
        )
    if profile is PageProcessingProfile.TABLE_LIKE:
        return QualityGateThresholds(
            max_low_confidence_ratio=0.40,
            max_fragmentation=0.48,
            max_single_char_token_ratio=0.32,
            max_symbol_only_token_ratio=0.22,
            max_over_segmentation=0.50,
            min_text_coverage=0.03,
            max_grid_intersection_ratio=0.60,
            max_near_duplicate_ratio=0.25,
            max_box_overlap_ratio=0.40,
            min_geometry_valid_ratio=0.90,
            min_median_words_per_line=0.0,
            max_median_words_per_line=16.0,
        )
    if profile is PageProcessingProfile.SPARSE_DOCUMENT:
        return QualityGateThresholds(
            max_low_confidence_ratio=0.50,
            max_fragmentation=0.55,
            max_single_char_token_ratio=0.45,
            max_symbol_only_token_ratio=0.30,
            max_over_segmentation=0.55,
            min_text_coverage=0.0,  # sparsity must not reject clean sparse pages
            max_grid_intersection_ratio=0.70,
            max_near_duplicate_ratio=0.30,
            max_box_overlap_ratio=0.40,
            min_geometry_valid_ratio=0.85,
            min_median_words_per_line=0.0,
            max_median_words_per_line=20.0,
            sparse_min_lines=0,
        )
    if profile is PageProcessingProfile.PHOTO_WITH_TEXT:
        return QualityGateThresholds(
            max_low_confidence_ratio=0.45,
            max_fragmentation=0.50,
            max_single_char_token_ratio=0.35,
            max_symbol_only_token_ratio=0.25,
            max_over_segmentation=0.50,
            min_text_coverage=0.02,
            max_grid_intersection_ratio=0.65,
            max_near_duplicate_ratio=0.28,
            max_box_overlap_ratio=0.40,
            min_geometry_valid_ratio=0.88,
            min_median_words_per_line=0.0,
            max_median_words_per_line=18.0,
        )
    return QualityGateThresholds(
        max_low_confidence_ratio=0.40,
        max_fragmentation=0.48,
        max_single_char_token_ratio=0.30,
        max_symbol_only_token_ratio=0.20,
        max_over_segmentation=0.48,
        min_text_coverage=0.015,
        max_grid_intersection_ratio=0.60,
        max_near_duplicate_ratio=0.25,
        max_box_overlap_ratio=0.35,
        min_geometry_valid_ratio=0.90,
        min_median_words_per_line=0.0,
        max_median_words_per_line=16.0,
    )


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = round((len(sorted_vals) - 1) * p)
    return sorted_vals[max(0, min(len(sorted_vals) - 1, idx))]


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return float((ordered[mid - 1] + ordered[mid]) / 2.0)


def _poly_area(poly: list[tuple[float, float]]) -> float:
    if len(poly) < 2:
        return 0.0
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    return max(0.0, (max(xs) - min(xs)) * (max(ys) - min(ys)))


def _poly_bbox(poly: list[tuple[float, float]]) -> tuple[float, float, float, float] | None:
    if not poly:
        return None
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, (ax1 - ax0) * (ay1 - ay0))
    area_b = max(0.0, (bx1 - bx0) * (by1 - by0))
    denom = area_a + area_b - inter
    return inter / denom if denom > 0 else 0.0


def build_quality_evidence(
    raw_lines: list[Any],
    *,
    page_number: int,
    ocr_pass: OcrPassKind,
    detector_limit_side: int,
    page_width: int,
    page_height: int,
    low_confidence_threshold: float,
    preprocessing_variant: PreprocessingVariant | None,
    profile: PageProfileResult,
    grid: GridInterferenceResult | None,
    route: str | None = None,
) -> PrintedOcrQualityEvidence:
    """Compute PrintedOcrQualityEvidence from raw OCR lines (no private logging)."""

    page_area = float(max(1, page_width * page_height))
    confidences: list[float] = []
    token_texts: list[str] = []
    line_texts: list[str] = []
    words_per_line: list[float] = []
    boxes: list[tuple[float, float, float, float]] = []
    coverage = 0.0
    valid_geom = 0
    oob = 0
    single_char_tokens = 0
    symbol_tokens = 0
    numeric_frags = 0
    single_char_lines = 0
    symbol_lines = 0

    for line in raw_lines:
        text = str(getattr(line, "text", "") or "").strip()
        score = float(getattr(line, "recognition_score", 0.0) or 0.0)
        confidences.append(score)
        line_texts.append(text)
        if len(text) == 1:
            single_char_lines += 1
        if text and _SYMBOL_RE.match(text):
            symbol_lines += 1
        tokens = text.split() if text else []
        words_per_line.append(float(len(tokens) if tokens else (1 if text else 0)))
        for tok in tokens or ([text] if text else []):
            token_texts.append(tok)
            if len(tok) == 1:
                single_char_tokens += 1
            if _SYMBOL_RE.match(tok):
                symbol_tokens += 1
            if _NUMERIC_RE.match(tok):
                numeric_frags += 1
        poly = getattr(line, "polygon_px", None) or []
        area = _poly_area(poly)
        coverage += area
        bbox = _poly_bbox(poly)
        if bbox is None:
            oob += 1
            continue
        x0, y0, x1, y1 = bbox
        if (
            x0 < -1
            or y0 < -1
            or x1 > page_width + 1
            or y1 > page_height + 1
            or x1 <= x0
            or y1 <= y0
        ):
            oob += 1
        else:
            valid_geom += 1
            boxes.append(bbox)

    n_lines = len(raw_lines)
    n_tokens = max(1, len(token_texts))
    ordered_conf = sorted(confidences)
    mean_conf = (sum(confidences) / len(confidences)) if confidences else None
    median_conf = _percentile(ordered_conf, 0.5)
    p10_conf = _percentile(ordered_conf, 0.1)
    low_ratio = (
        sum(1 for c in confidences if c < low_confidence_threshold) / n_lines if n_lines else 0.0
    )

    # Overlap / near-duplicate among boxes (sampled pairwise for bounded cost).
    overlap_hits = 0
    dup_hits = 0
    pair_count = 0
    limit_pairs = min(len(boxes), 80)
    for i in range(limit_pairs):
        for j in range(i + 1, limit_pairs):
            pair_count += 1
            iou = _iou(boxes[i], boxes[j])
            if iou >= 0.35:
                overlap_hits += 1
            if iou >= 0.85:
                dup_hits += 1
    box_overlap = overlap_hits / pair_count if pair_count else 0.0
    near_dup = dup_hits / pair_count if pair_count else 0.0

    single_char_token_ratio = single_char_tokens / n_tokens
    symbol_token_ratio = symbol_tokens / n_tokens
    numeric_ratio = numeric_frags / n_tokens
    single_char_line_ratio = single_char_lines / n_lines if n_lines else 0.0
    symbol_line_ratio = symbol_lines / n_lines if n_lines else 0.0
    median_token_len = _median([float(len(t)) for t in token_texts]) if token_texts else 0.0
    median_wpl = _median(words_per_line)

    # Fragmentation: short tokens + many single-char lines + low median words/line.
    fragmentation = min(
        1.0,
        0.45 * single_char_token_ratio
        + 0.25 * single_char_line_ratio
        + 0.20 * (1.0 if median_token_len < 2.5 else max(0.0, (3.5 - median_token_len) / 3.5))
        + 0.10 * (1.0 if median_wpl < 1.2 and n_lines > 20 else 0.0),
    )
    over_seg = min(
        1.0,
        0.5 * (n_lines / max(1.0, sum(words_per_line) + 1.0) if n_lines > 30 else 0.0)
        + 0.3 * single_char_line_ratio
        + 0.2 * box_overlap,
    )
    if n_lines > 200 and median_wpl < 1.5:
        fragmentation = min(1.0, fragmentation + 0.15)
        over_seg = min(1.0, over_seg + 0.15)

    coverage_ratio = min(1.0, coverage / page_area)
    geom_valid = valid_geom / n_lines if n_lines else 1.0
    oob_ratio = oob / n_lines if n_lines else 0.0
    grid_ratio = float(grid.grid_intersection_ratio) if grid is not None else 0.0

    evidence = PrintedOcrQualityEvidence(
        policy_version=QUALITY_POLICY_VERSION,
        page_number=page_number,
        route=route,
        ocr_pass=ocr_pass,
        detector_limit_side=detector_limit_side,
        preprocessing_variant=preprocessing_variant,
        page_profile=profile.page_profile,
        profile_confidence=profile.profile_confidence,
        profile_reason_codes=list(profile.profile_reason_codes),
        detected_region_count=n_lines,
        line_count=n_lines,
        word_count=len(token_texts),
        mean_confidence=mean_conf,
        median_confidence=median_conf,
        p10_confidence=p10_conf,
        low_confidence_ratio=float(low_ratio),
        single_character_token_ratio=float(single_char_token_ratio),
        single_character_line_ratio=float(single_char_line_ratio),
        symbol_only_token_ratio=float(symbol_token_ratio),
        symbol_only_line_ratio=float(symbol_line_ratio),
        numeric_fragment_ratio=float(numeric_ratio),
        median_token_length=float(median_token_len),
        median_words_per_line=float(median_wpl),
        fragmentation_score=float(fragmentation),
        over_segmentation_score=float(over_seg),
        box_overlap_ratio=float(min(1.0, box_overlap)),
        near_duplicate_box_ratio=float(min(1.0, near_dup)),
        grid_intersection_ratio=float(grid_ratio),
        text_coverage_ratio=float(coverage_ratio),
        geometry_valid_ratio=float(geom_valid),
        out_of_bounds_ratio=float(oob_ratio),
    )
    return apply_primary_quality_gate(evidence)


def apply_primary_quality_gate(evidence: PrintedOcrQualityEvidence) -> PrintedOcrQualityEvidence:
    """Apply versioned primary-pass acceptance policy. Confidence alone cannot pass."""

    thresholds = thresholds_for_profile(evidence.page_profile)
    reasons: list[str] = []

    if evidence.geometry_valid_ratio < thresholds.min_geometry_valid_ratio:
        reasons.append("insufficient_valid_geometry")
    if evidence.low_confidence_ratio > thresholds.max_low_confidence_ratio:
        reasons.append("high_low_confidence_ratio")
    if evidence.fragmentation_score > thresholds.max_fragmentation:
        reasons.append("excessive_fragmentation")
    if evidence.single_character_token_ratio > thresholds.max_single_char_token_ratio:
        reasons.append("excessive_single_character_tokens")
    if evidence.symbol_only_token_ratio > thresholds.max_symbol_only_token_ratio:
        reasons.append("excessive_symbol_only_tokens")
    if evidence.over_segmentation_score > thresholds.max_over_segmentation:
        reasons.append("excessive_over_segmentation")
    if (
        evidence.page_profile is not PageProcessingProfile.SPARSE_DOCUMENT
        and evidence.text_coverage_ratio < thresholds.min_text_coverage
        and evidence.line_count > 0
    ):
        reasons.append("inadequate_text_coverage")
    if evidence.grid_intersection_ratio > thresholds.max_grid_intersection_ratio:
        reasons.append("excessive_grid_interference")
    if evidence.near_duplicate_box_ratio > thresholds.max_near_duplicate_ratio:
        reasons.append("excessive_near_duplicate_boxes")
    if evidence.box_overlap_ratio > thresholds.max_box_overlap_ratio:
        reasons.append("excessive_box_overlap")
    if evidence.median_words_per_line > thresholds.max_median_words_per_line:
        reasons.append("implausible_words_per_line")

    # Dense forms with many lines but tiny median token length are fragmented even if
    # mean confidence looks acceptable.
    if (
        evidence.page_profile is PageProcessingProfile.DENSE_FORM
        and evidence.line_count >= 80
        and evidence.median_token_length < 2.8
        and evidence.fragmentation_score >= 0.35
        and "excessive_fragmentation" not in reasons
    ):
        reasons.append("dense_form_fragmentation")

    gate_passed = len(reasons) == 0
    # Empty page: gate may pass (no text) — fallback not recommended solely for emptiness.
    if evidence.line_count == 0:
        gate_passed = True
        reasons = []

    status = derive_quality_status(evidence, gate_passed=gate_passed, reason_codes=reasons)
    return evidence.model_copy(
        update={
            "fallback_recommended": (not gate_passed) and evidence.line_count > 0,
            "fallback_reason_codes": reasons,
            "quality_gate_passed": gate_passed,
            "quality_status": status,
        }
    )


def derive_quality_status(
    evidence: PrintedOcrQualityEvidence,
    *,
    gate_passed: bool,
    reason_codes: list[str],
) -> OcrQualityStatus:
    if evidence.line_count == 0:
        return OcrQualityStatus.INSUFFICIENT
    if gate_passed and evidence.fragmentation_score < 0.25 and evidence.low_confidence_ratio < 0.15:
        return OcrQualityStatus.GOOD
    if gate_passed:
        return OcrQualityStatus.USABLE_WITH_WARNINGS
    if evidence.fragmentation_score >= 0.7 or evidence.geometry_valid_ratio < 0.7:
        return OcrQualityStatus.INSUFFICIENT
    if reason_codes:
        return OcrQualityStatus.LOW_QUALITY
    return OcrQualityStatus.USABLE_WITH_WARNINGS


def _distribution(evidence: PrintedOcrQualityEvidence) -> ConfidenceDistribution:
    return ConfidenceDistribution(
        mean=evidence.mean_confidence,
        median=evidence.median_confidence,
        p10=evidence.p10_confidence,
        low_confidence_ratio=evidence.low_confidence_ratio,
    )


def _quality_score(evidence: PrintedOcrQualityEvidence) -> float:
    """Higher is better composite for selection (not displayed as accuracy)."""

    return (
        0.25 * (1.0 - evidence.fragmentation_score)
        + 0.15 * (1.0 - evidence.over_segmentation_score)
        + 0.15 * evidence.geometry_valid_ratio
        + 0.15 * min(1.0, evidence.text_coverage_ratio * 4.0)
        + 0.10 * (1.0 - evidence.low_confidence_ratio)
        + 0.10 * (1.0 - evidence.single_character_token_ratio)
        + 0.10 * (1.0 - evidence.symbol_only_token_ratio)
    )


def mandatory_safety_passed(evidence: PrintedOcrQualityEvidence) -> bool:
    return (
        evidence.geometry_valid_ratio >= 0.75
        and evidence.out_of_bounds_ratio <= 0.25
        and evidence.line_count >= 0
    )


def compare_ocr_passes(
    primary: PrintedOcrQualityEvidence,
    fallback: PrintedOcrQualityEvidence | None,
    *,
    primary_valid_words: int,
    fallback_valid_words: int,
) -> OcrPassComparison:
    """Select fallback only when measurable improvement and mandatory safety pass."""

    if fallback is None:
        return OcrPassComparison(
            primary_quality=primary,
            fallback_quality=None,
            primary_valid_words=primary_valid_words,
            fallback_valid_words=0,
            primary_confidence_distribution=_distribution(primary),
            fallback_confidence_distribution=None,
            primary_fragmentation=primary.fragmentation_score,
            fallback_fragmentation=None,
            primary_geometry_quality=primary.geometry_valid_ratio,
            fallback_geometry_quality=None,
            primary_text_coverage=primary.text_coverage_ratio,
            fallback_text_coverage=None,
            selected_pass=OcrPassKind.PRIMARY,
            selection_reason_codes=["fallback_unavailable"],
        )

    reasons: list[str] = []
    primary_score = _quality_score(primary)
    fallback_score = _quality_score(fallback)
    improvement = fallback_score - primary_score
    frag_improvement = primary.fragmentation_score - fallback.fragmentation_score

    select_fallback = False
    if not mandatory_safety_passed(fallback):
        reasons.append("fallback_failed_mandatory_safety")
    elif improvement < 0.03 and frag_improvement < 0.05:
        reasons.append("fallback_no_measured_improvement")
    elif fallback.fragmentation_score > primary.fragmentation_score + 0.05:
        reasons.append("fallback_worse_fragmentation")
    else:
        # Require measured improvement — never select solely because image is larger.
        if (
            improvement >= 0.03
            or frag_improvement >= 0.08
            or (
                fallback_valid_words > primary_valid_words * 1.05
                and fallback.single_character_token_ratio
                <= primary.single_character_token_ratio + 0.02
                and fallback.fragmentation_score <= primary.fragmentation_score
            )
        ):
            select_fallback = True
            reasons.append("fallback_measured_quality_improvement")
            if frag_improvement >= 0.08:
                reasons.append("fallback_lower_fragmentation")
        else:
            reasons.append("fallback_no_measured_improvement")

    selected = OcrPassKind.FALLBACK if select_fallback else OcrPassKind.PRIMARY
    if not select_fallback and "fallback_no_measured_improvement" in reasons:
        reasons.append("primary_retained")

    return OcrPassComparison(
        primary_quality=primary,
        fallback_quality=fallback,
        primary_valid_words=primary_valid_words,
        fallback_valid_words=fallback_valid_words,
        primary_confidence_distribution=_distribution(primary),
        fallback_confidence_distribution=_distribution(fallback),
        primary_fragmentation=primary.fragmentation_score,
        fallback_fragmentation=fallback.fragmentation_score,
        primary_geometry_quality=primary.geometry_valid_ratio,
        fallback_geometry_quality=fallback.geometry_valid_ratio,
        primary_text_coverage=primary.text_coverage_ratio,
        fallback_text_coverage=fallback.text_coverage_ratio,
        selected_pass=selected,
        selection_reason_codes=reasons,
    )


def count_valid_words(raw_lines: list[Any], *, min_score: float) -> int:
    count = 0
    for line in raw_lines:
        words = getattr(line, "words", None) or []
        if words:
            for word in words:
                text = str(getattr(word, "text", "") or "").strip()
                score = float(getattr(word, "score", 0.0) or 0.0)
                if text and score >= min_score and any(ch.isalnum() for ch in text):
                    count += 1
        else:
            text = str(getattr(line, "text", "") or "").strip()
            score = float(getattr(line, "recognition_score", 0.0) or 0.0)
            if text and score >= min_score:
                count += len([t for t in text.split() if any(ch.isalnum() for ch in t)])
    return count

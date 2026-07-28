"""Near-overprint duplicate detection, multi-path hard reject, and layer collapse.

Phase 3.5: PATH A (widespread), PATH B (coherent partial/region), PATH C (safe
collapse). Dominant single-offset support is informational only.
"""

from __future__ import annotations

import math
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from backend.app.contracts.native import (
    DUPLICATE_LAYER_POLICY_VERSION,
    DuplicateLayerEvidence,
    DuplicateRuleRecord,
)
from backend.app.extraction.native.models import RawCharCandidate, RawWordCandidate

DEFAULT_IOU_THRESHOLD = 0.35
DEFAULT_CENTRE_DISTANCE_FACTOR = 0.35
DEFAULT_CENTRE_DISTANCE_CAP_POINTS = 3.5
DEFAULT_SIZE_SIMILARITY = 0.40
DEFAULT_OFFSET_BIN_POINTS = 0.25
DEFAULT_CROSS_COVERAGE_MIN = 0.85
DEFAULT_COVERAGE_GAP_MAX = 0.05
DEFAULT_MIN_WORD_SPAN = 3
DEFAULT_MIN_LINE_SPAN = 2
DEFAULT_OFFSET_CLUSTER_ABS_TOL = 0.75
DEFAULT_OFFSET_CLUSTER_SIZE_FACTOR = 0.08
DEFAULT_OFFSET_CLUSTER_TOP_K = 3
DEFAULT_PATH_B_MIN_COVERAGE = 0.90
DEFAULT_PATH_B_MIN_MATCHES = 48
DEFAULT_PATH_B_MIN_DUPLICATE_LINES = 2
DEFAULT_PATH_B_MIN_DUPLICATE_REGIONS = 1
DEFAULT_REGION_MIN_CHARS = 12
DEFAULT_REGION_SEVERE_RATIO = 0.50
DEFAULT_REGION_MIN_MATCHED = 8
DEFAULT_GEOMETRIC_INTERLEAVE_RATIO = 0.12


@dataclass(frozen=True, slots=True)
class NearOverprintMetrics:
    """Pre-clean near-overprint diagnostics (no extracted text)."""

    strict_duplicate_ratio: float
    near_overprint_duplicate_ratio: float
    duplicate_layer_count: int
    dominant_duplicate_offset_x: float
    dominant_duplicate_offset_y: float
    duplicate_layer_coverage_ratio: float = 0.0
    matched_near_duplicate_count: int = 0
    dominant_offset_support_ratio: float = 0.0
    matched_word_span: int = 0
    matched_line_span: int = 0
    composite_duplicate_layer_evidence: bool = False
    top_offset_cluster_support_ratio: float = 0.0
    top_k_offset_cluster_support_ratio: float = 0.0
    offset_cluster_count: int = 0
    duplicate_line_count: int = 0
    duplicate_region_count: int = 0
    page_vertical_span_ratio: float = 0.0
    page_horizontal_span_ratio: float = 0.0
    hard_rule_path: str = "none"
    hard_rule_explanation: tuple[str, ...] = ()
    duplicate_layer_evidence: object | None = None  # DuplicateLayerEvidence when built


@dataclass(frozen=True, slots=True)
class NearOverprintOutcome:
    """Result of detection and optional cleaning."""

    metrics: NearOverprintMetrics
    selection: Literal["none", "cleaned", "ambiguous"]
    characters: list[RawCharCandidate]
    words: list[RawWordCandidate]


@dataclass(frozen=True, slots=True)
class CompositeThresholds:
    max_near_overprint_ratio: float = 0.08
    max_duplicate_layer_coverage_ratio: float = 0.70
    min_near_duplicate_match_count: int = 24
    min_dominant_offset_support_ratio: float = 0.55  # informational only
    min_word_span: int = DEFAULT_MIN_WORD_SPAN
    min_line_span: int = DEFAULT_MIN_LINE_SPAN
    offset_cluster_abs_tol: float = DEFAULT_OFFSET_CLUSTER_ABS_TOL
    offset_cluster_size_factor: float = DEFAULT_OFFSET_CLUSTER_SIZE_FACTOR
    offset_cluster_top_k: int = DEFAULT_OFFSET_CLUSTER_TOP_K
    path_b_min_coverage: float = DEFAULT_PATH_B_MIN_COVERAGE
    path_b_min_matches: int = DEFAULT_PATH_B_MIN_MATCHES
    path_b_min_duplicate_lines: int = DEFAULT_PATH_B_MIN_DUPLICATE_LINES
    path_b_min_duplicate_regions: int = DEFAULT_PATH_B_MIN_DUPLICATE_REGIONS
    region_min_chars: int = DEFAULT_REGION_MIN_CHARS
    region_severe_ratio: float = DEFAULT_REGION_SEVERE_RATIO
    region_min_matched: int = DEFAULT_REGION_MIN_MATCHED


@dataclass(frozen=True, slots=True)
class HardRuleCondition:
    """Legacy condition row; prefer DuplicateRuleRecord on DuplicateLayerEvidence."""

    metric: str
    value: str
    threshold: str
    passed: bool
    mandatory: bool


@dataclass(frozen=True, slots=True)
class HardRuleExplanation:
    path: str
    final_hard_rejection: bool
    conditions: tuple[HardRuleCondition, ...] = field(default_factory=tuple)

    def format_lines(self) -> tuple[str, ...]:
        lines = [f"Duplicate-layer hard rejection path={self.path}:"]
        for c in self.conditions:
            status = "PASS" if c.passed else "FAIL"
            kind = "mandatory" if c.mandatory else "informational"
            lines.append(f"- {c.metric}: {c.value} {c.threshold}: {status} ({kind})")
        lines.append(f"- final hard rejection: {str(self.final_hard_rejection).upper()}")
        return tuple(lines)


def _path_a_match_floor(metrics: NearOverprintMetrics, thr: CompositeThresholds) -> int:
    min_matches = thr.min_near_duplicate_match_count
    if metrics.duplicate_layer_coverage_ratio >= 0.90 and metrics.duplicate_layer_count >= 2:
        min_matches = min(min_matches, 8)
    return min_matches


def _path_b_match_floor(metrics: NearOverprintMetrics, thr: CompositeThresholds) -> int:
    """Path B match floor. Adaptive only when structural line/region evidence exists."""

    structure_ok = (
        metrics.duplicate_line_count >= thr.path_b_min_duplicate_lines
        or metrics.duplicate_region_count >= thr.path_b_min_duplicate_regions
    )
    match_floor = thr.path_b_min_matches
    if not structure_ok:
        return match_floor
    regional_match_floor = max(12, thr.region_min_matched * 2)
    if metrics.duplicate_layer_coverage_ratio >= 0.95:
        match_floor = min(match_floor, thr.min_near_duplicate_match_count)
    if metrics.duplicate_layer_coverage_ratio >= thr.path_b_min_coverage:
        match_floor = min(match_floor, regional_match_floor)
    return match_floor


def _span_ok(metrics: NearOverprintMetrics, thr: CompositeThresholds) -> bool:
    return (
        metrics.matched_word_span >= thr.min_word_span
        or metrics.matched_line_span >= thr.min_line_span
        or metrics.duplicate_line_count >= thr.path_b_min_duplicate_lines
        or (
            metrics.duplicate_layer_coverage_ratio >= 0.90
            and metrics.matched_near_duplicate_count >= 8
        )
    )


def _rule(
    *,
    rule_id: str,
    metric_name: str,
    actual_value: float | int | bool | str,
    operator: str,
    threshold: float | int | bool | str,
    passed: bool,
    mandatory: bool,
    applies_to_path: Literal["A", "B", "both", "info"],
    explanation: str,
) -> DuplicateRuleRecord:
    return DuplicateRuleRecord(
        rule_id=rule_id,
        metric_name=metric_name,
        actual_value=actual_value,
        operator=operator,
        threshold=threshold,
        mandatory=mandatory,
        passed=passed,
        applies_to_path=applies_to_path,
        explanation=explanation,
    )


def build_duplicate_layer_evidence(
    metrics: NearOverprintMetrics,
    thr: CompositeThresholds,
    *,
    policy_version: str = DUPLICATE_LAYER_POLICY_VERSION,
) -> DuplicateLayerEvidence:
    """Build the single canonical evidence object; decision equals displayed rules."""

    path_a_match_floor = _path_a_match_floor(metrics, thr)
    path_a_rules = [
        _rule(
            rule_id="path_a_matches",
            metric_name="matched_near_duplicate_count",
            actual_value=metrics.matched_near_duplicate_count,
            operator=">=",
            threshold=path_a_match_floor,
            passed=metrics.matched_near_duplicate_count >= path_a_match_floor,
            mandatory=True,
            applies_to_path="A",
            explanation="Minimum near-overprint match count for Path A.",
        ),
        _rule(
            rule_id="path_a_near_ratio",
            metric_name="near_overprint_duplicate_ratio",
            actual_value=round(metrics.near_overprint_duplicate_ratio, 6),
            operator=">",
            threshold=thr.max_near_overprint_ratio,
            passed=metrics.near_overprint_duplicate_ratio > thr.max_near_overprint_ratio,
            mandatory=True,
            applies_to_path="A",
            explanation="Global near-overprint ratio must exceed Path A cap.",
        ),
        _rule(
            rule_id="path_a_coverage",
            metric_name="duplicate_layer_coverage_ratio",
            actual_value=round(metrics.duplicate_layer_coverage_ratio, 6),
            operator=">",
            threshold=thr.max_duplicate_layer_coverage_ratio,
            passed=metrics.duplicate_layer_coverage_ratio > thr.max_duplicate_layer_coverage_ratio,
            mandatory=True,
            applies_to_path="A",
            explanation="Layer coverage must exceed Path A coverage floor.",
        ),
        _rule(
            rule_id="path_a_span",
            metric_name="structure_span",
            actual_value=(
                f"word_span={metrics.matched_word_span};"
                f"line_span={metrics.matched_line_span};"
                f"dup_lines={metrics.duplicate_line_count}"
            ),
            operator="satisfies",
            threshold=(
                f"word>={thr.min_word_span}|line>={thr.min_line_span}|"
                f"dup_lines>={thr.path_b_min_duplicate_lines}|coverage>=0.9&matches>=8"
            ),
            passed=_span_ok(metrics, thr),
            mandatory=True,
            applies_to_path="A",
            explanation="Path A requires multi-token or multi-line structure.",
        ),
    ]
    path_a_satisfied = all(r.passed for r in path_a_rules if r.mandatory)

    coverage_ok = metrics.duplicate_layer_coverage_ratio >= thr.path_b_min_coverage or (
        metrics.duplicate_layer_coverage_ratio > thr.max_duplicate_layer_coverage_ratio
        and metrics.duplicate_region_count >= thr.path_b_min_duplicate_regions
    )
    structure_ok = (
        metrics.duplicate_line_count >= thr.path_b_min_duplicate_lines
        or metrics.duplicate_region_count >= thr.path_b_min_duplicate_regions
    )
    path_b_match_floor = _path_b_match_floor(metrics, thr)
    matches_ok = metrics.matched_near_duplicate_count >= path_b_match_floor
    geometry_ok = metrics.matched_near_duplicate_count > 0

    path_b_rules = [
        _rule(
            rule_id="path_b_coverage",
            metric_name="duplicate_layer_coverage_ratio",
            actual_value=round(metrics.duplicate_layer_coverage_ratio, 6),
            operator="satisfies",
            threshold=(
                f">={thr.path_b_min_coverage} OR "
                f"(>{thr.max_duplicate_layer_coverage_ratio} AND regions>="
                f"{thr.path_b_min_duplicate_regions})"
            ),
            passed=coverage_ok,
            mandatory=True,
            applies_to_path="B",
            explanation="Path B requires high layer coverage or coverage with regions.",
        ),
        _rule(
            rule_id="path_b_matches",
            metric_name="matched_near_duplicate_count",
            actual_value=metrics.matched_near_duplicate_count,
            operator=">=",
            threshold=path_b_match_floor,
            passed=matches_ok,
            mandatory=True,
            applies_to_path="B",
            explanation=("Path B match floor (adaptive only when duplicate lines/regions exist)."),
        ),
        _rule(
            rule_id="path_b_structure",
            metric_name="duplicate_line_or_region_count",
            actual_value=(
                f"dup_lines={metrics.duplicate_line_count};"
                f"dup_regions={metrics.duplicate_region_count}"
            ),
            operator="satisfies",
            threshold=(
                f"dup_lines>={thr.path_b_min_duplicate_lines} OR "
                f"dup_regions>={thr.path_b_min_duplicate_regions}"
            ),
            passed=structure_ok,
            mandatory=True,
            applies_to_path="B",
            explanation=(
                "Path B requires coherent line/region structure; sparse character "
                "matches alone are insufficient."
            ),
        ),
        _rule(
            rule_id="path_b_geometry",
            metric_name="geometric_overlap_present",
            actual_value=geometry_ok,
            operator="==",
            threshold=True,
            passed=geometry_ok,
            mandatory=True,
            applies_to_path="B",
            explanation="At least one near-overprint pair must be present.",
        ),
        _rule(
            rule_id="path_b_info_lines",
            metric_name="duplicate_line_count",
            actual_value=metrics.duplicate_line_count,
            operator=">=",
            threshold=thr.path_b_min_duplicate_lines,
            passed=metrics.duplicate_line_count >= thr.path_b_min_duplicate_lines,
            mandatory=False,
            applies_to_path="info",
            explanation="Informational line count (structure rule is authoritative).",
        ),
        _rule(
            rule_id="path_b_info_regions",
            metric_name="duplicate_region_count",
            actual_value=metrics.duplicate_region_count,
            operator=">=",
            threshold=thr.path_b_min_duplicate_regions,
            passed=metrics.duplicate_region_count >= thr.path_b_min_duplicate_regions,
            mandatory=False,
            applies_to_path="info",
            explanation="Informational region count (structure rule is authoritative).",
        ),
    ]
    # Informational offset support (never decides path alone).
    info_rules = [
        _rule(
            rule_id="info_dominant_offset_support",
            metric_name="dominant_offset_support_ratio",
            actual_value=round(metrics.dominant_offset_support_ratio, 6),
            operator="informational",
            threshold=thr.min_dominant_offset_support_ratio,
            passed=True,
            mandatory=False,
            applies_to_path="info",
            explanation="Informational only; not a Path A/B mandatory gate.",
        ),
        _rule(
            rule_id="info_top_k_offset_support",
            metric_name="top_k_offset_cluster_support_ratio",
            actual_value=round(metrics.top_k_offset_cluster_support_ratio, 6),
            operator="informational",
            threshold="collapse aid",
            passed=True,
            mandatory=False,
            applies_to_path="info",
            explanation="Informational / Path C collapse aid.",
        ),
    ]
    path_b_rules.extend(info_rules)
    path_b_satisfied = all(r.passed for r in path_b_rules if r.mandatory)

    selected: Literal["A", "B", "none"]
    if path_a_satisfied:
        selected = "A"
    elif path_b_satisfied:
        selected = "B"
    else:
        selected = "none"

    return DuplicateLayerEvidence(
        policy_version=policy_version,
        strict_duplicate_ratio=metrics.strict_duplicate_ratio,
        near_overprint_duplicate_ratio=metrics.near_overprint_duplicate_ratio,
        duplicate_layer_coverage_ratio=metrics.duplicate_layer_coverage_ratio,
        matched_near_duplicate_count=metrics.matched_near_duplicate_count,
        duplicate_line_count=metrics.duplicate_line_count,
        duplicate_region_count=metrics.duplicate_region_count,
        dominant_offset_x=metrics.dominant_duplicate_offset_x,
        dominant_offset_y=metrics.dominant_duplicate_offset_y,
        dominant_offset_support_ratio=metrics.dominant_offset_support_ratio,
        top_k_offset_cluster_support_ratio=metrics.top_k_offset_cluster_support_ratio,
        offset_cluster_count=metrics.offset_cluster_count,
        geometric_overlap_present=geometry_ok,
        path_a_rules=path_a_rules,
        path_b_rules=path_b_rules,
        path_a_satisfied=path_a_satisfied,
        path_b_satisfied=path_b_satisfied,
        selected_path=selected,
        hard_rejection=selected in {"A", "B"},
    )


def evidence_to_explanation(evidence: DuplicateLayerEvidence) -> HardRuleExplanation:
    """Derive legacy explanation lines from canonical evidence (no re-decision)."""

    conditions: list[HardRuleCondition] = []
    for rule in [*evidence.path_a_rules, *evidence.path_b_rules]:
        conditions.append(
            HardRuleCondition(
                metric=rule.metric_name,
                value=str(rule.actual_value),
                threshold=f"{rule.operator} {rule.threshold}",
                passed=rule.passed,
                mandatory=rule.mandatory,
            )
        )
    conditions.append(
        HardRuleCondition(
            metric="path_a_widespread",
            value=str(evidence.path_a_satisfied),
            threshold="PATH A",
            passed=evidence.path_a_satisfied,
            mandatory=True,
        )
    )
    conditions.append(
        HardRuleCondition(
            metric="path_b_coherent_partial",
            value=str(evidence.path_b_satisfied),
            threshold="PATH B",
            passed=evidence.path_b_satisfied,
            mandatory=True,
        )
    )
    return HardRuleExplanation(
        path=evidence.selected_path,
        final_hard_rejection=evidence.hard_rejection,
        conditions=tuple(conditions),
    )


def path_a_widespread_duplication(metrics: NearOverprintMetrics, thr: CompositeThresholds) -> bool:
    """PATH A: substantial page-level near-overprint duplication."""

    return build_duplicate_layer_evidence(metrics, thr).path_a_satisfied


def path_b_coherent_partial_layer(metrics: NearOverprintMetrics, thr: CompositeThresholds) -> bool:
    """PATH B: coherent partial duplicate layer with line/region structure."""

    return build_duplicate_layer_evidence(metrics, thr).path_b_satisfied


def composite_duplicate_layer_evidence(
    metrics: NearOverprintMetrics,
    thresholds: CompositeThresholds,
) -> bool:
    """True when PATH A or PATH B fires. Dominant-offset support is not required."""

    evidence = build_duplicate_layer_evidence(metrics, thresholds)
    return evidence.hard_rejection


def explain_duplicate_layer_hard_rejection(
    metrics: NearOverprintMetrics,
    thresholds: CompositeThresholds,
    *,
    path: str | None = None,
) -> HardRuleExplanation:
    """Structured hard-rule explanation derived from canonical evidence."""

    evidence = build_duplicate_layer_evidence(metrics, thresholds)
    explanation = evidence_to_explanation(evidence)
    if path is not None and path != explanation.path:
        # Path label must match decision; ignore stale callers.
        _ = path
    return explanation


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _centre(ch: RawCharCandidate) -> tuple[float, float]:
    return ((ch.x0 + ch.x1) / 2.0, (ch.top + ch.bottom) / 2.0)


def _width(ch: RawCharCandidate) -> float:
    return max(ch.x1 - ch.x0, 0.0)


def _height(ch: RawCharCandidate) -> float:
    return max(ch.bottom - ch.top, 0.0)


def _iou(a: RawCharCandidate, b: RawCharCandidate) -> float:
    ix0 = max(a.x0, b.x0)
    iy0 = max(a.top, b.top)
    ix1 = min(a.x1, b.x1)
    iy1 = min(a.bottom, b.bottom)
    iw = max(0.0, ix1 - ix0)
    ih = max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0.0:
        return 0.0
    area_a = max(_width(a) * _height(a), 1e-9)
    area_b = max(_width(b) * _height(b), 1e-9)
    union = area_a + area_b - inter
    return inter / max(union, 1e-9)


def _dims_similar(a: RawCharCandidate, b: RawCharCandidate, *, max_rel: float) -> bool:
    wa, wb = _width(a), _width(b)
    ha, hb = _height(a), _height(b)
    sa, sb = max(a.size, 1e-6), max(b.size, 1e-6)
    size_rel = abs(sa - sb) / max(sa, sb)
    if size_rel > max_rel and max(wa, wb) > 0.5:
        w_rel = abs(wa - wb) / max(wa, wb, 1e-6)
        h_rel = abs(ha - hb) / max(ha, hb, 1e-6)
        if w_rel > max_rel or h_rel > max_rel:
            return False
    elif size_rel > max_rel:
        return False
    return True


def _orientation_bucket(ch: RawCharCandidate) -> tuple[bool, int]:
    return (ch.upright, round(ch.rotation_degrees / 5.0))


def _are_near_overprint_pair(
    a: RawCharCandidate,
    b: RawCharCandidate,
    *,
    iou_threshold: float,
    centre_factor: float,
    centre_cap: float,
    size_similarity: float,
) -> bool:
    if _nfc(a.text) != _nfc(b.text):
        return False
    if a.text.isspace():
        return False
    if _orientation_bucket(a) != _orientation_bucket(b):
        return False
    if not _dims_similar(a, b, max_rel=size_similarity):
        return False
    if _iou(a, b) >= iou_threshold:
        return True
    cax, cay = _centre(a)
    cbx, cby = _centre(b)
    dist = math.hypot(cax - cbx, cay - cby)
    limit = min(centre_cap, centre_factor * max(a.size, b.size, 1.0))
    return dist <= limit


def _bin_offset(dx: float, dy: float, bin_size: float) -> tuple[float, float]:
    return (round(dx / bin_size) * bin_size, round(dy / bin_size) * bin_size)


def _font_key(ch: RawCharCandidate) -> str:
    return (ch.fontname or "").strip() or "__missing__"


def _size_bucket(ch: RawCharCandidate) -> int:
    return round(ch.size * 2.0)


def _layer_signature(ch: RawCharCandidate) -> tuple[str, int, bool | None]:
    return (_font_key(ch), _size_bucket(ch), ch.tagged)


def rebuild_words_from_characters(
    characters: list[RawCharCandidate],
    *,
    x_tolerance: float = 3.0,
    y_tolerance: float = 3.0,
) -> list[RawWordCandidate]:
    if not characters:
        return []

    indexed = list(enumerate(characters))
    indexed.sort(key=lambda item: (item[1].top, item[1].x0, item[0]))

    lines: list[list[tuple[int, RawCharCandidate]]] = []
    for item in indexed:
        ch = item[1]
        if ch.text.isspace():
            continue
        placed = False
        for line in lines:
            tops = [c.top for _, c in line]
            median_top = sorted(tops)[len(tops) // 2]
            if abs(ch.top - median_top) <= y_tolerance:
                line.append(item)
                placed = True
                break
        if not placed:
            lines.append([item])

    words: list[RawWordCandidate] = []
    word_index = 0
    for line in lines:
        line.sort(key=lambda item: (item[1].x0, item[0]))
        current: list[tuple[int, RawCharCandidate]] = []
        for item in line:
            if not current:
                current = [item]
                continue
            prev = current[-1][1]
            gap = item[1].x0 - prev.x1
            if gap > x_tolerance:
                words.append(_word_from_chars(current, word_index))
                word_index += 1
                current = [item]
            else:
                current.append(item)
        if current:
            words.append(_word_from_chars(current, word_index))
            word_index += 1
    return words


def _word_from_chars(
    items: list[tuple[int, RawCharCandidate]], sequence_index: int
) -> RawWordCandidate:
    chars = [c for _, c in items]
    indices = [i for i, _ in items]
    fontnames = sorted({c.fontname for c in chars if c.fontname})
    sizes = sorted({c.size for c in chars})
    return RawWordCandidate(
        text="".join(c.text for c in chars),
        x0=min(c.x0 for c in chars),
        x1=max(c.x1 for c in chars),
        top=min(c.top for c in chars),
        bottom=max(c.bottom for c in chars),
        sequence_index=sequence_index,
        char_indices=indices,
        fontnames=fontnames,
        sizes=sizes,
        upright=all(c.upright for c in chars),
    )


def _renumber_characters(characters: list[RawCharCandidate]) -> list[RawCharCandidate]:
    ordered = sorted(characters, key=lambda c: (c.top, c.x0, c.sequence_index))
    return [
        RawCharCandidate(
            text=c.text,
            fontname=c.fontname,
            size=c.size,
            upright=c.upright,
            rotation_degrees=c.rotation_degrees,
            x0=c.x0,
            x1=c.x1,
            top=c.top,
            bottom=c.bottom,
            sequence_index=i,
            tagged=c.tagged,
        )
        for i, c in enumerate(ordered)
    ]


def interleaved_double_ratio(text: str) -> float:
    """Fraction of alphanumeric runs that look like RRuunn-style doubles."""

    if not text:
        return 0.0
    doubles = 0
    alnum = 0
    i = 0
    while i + 1 < len(text):
        if text[i].isalnum():
            alnum += 1
        if text[i] == text[i + 1] and text[i].isalnum():
            doubles += 1
            i += 2
        else:
            i += 1
    return doubles / max(alnum, 1)


def max_consecutive_double_pair_run(text: str) -> int:
    """Longest run of consecutive doubled alphanumeric pairs (``AABBCC…``).

    Distinguishes overprint ``SSYYNN`` bands from English words like ``bookkeeper``
    (isolated legitimate double letters; run length 1).
    """

    if not text:
        return 0
    best = 0
    run = 0
    i = 0
    while i + 1 < len(text):
        a, b = text[i], text[i + 1]
        if a.isalnum() and a == b:
            run += 1
            best = max(best, run)
            i += 2
            continue
        run = 0
        i += 1
    return best


def max_window_interleaved_double_ratio(text: str, *, window: int = 48) -> float:
    """Worst-case interleaved-double ratio in any sliding window.

    Prefer :func:`max_consecutive_double_pair_run` for accept/reject gates that must
    tolerate English double letters; this helper remains for diagnostics.
    """

    if not text:
        return 0.0
    if window < 8:
        window = 8
    if len(text) <= window:
        return interleaved_double_ratio(text)
    best = 0.0
    for start in range(0, len(text) - window + 1):
        best = max(best, interleaved_double_ratio(text[start : start + window]))
        if best >= 1.0:
            return 1.0
    return best


# Dense AABB overprint bands (header/footer) vs isolated English doubles.
_MIN_AABB_RUN_FOR_REJECT = 4


def geometric_interleave_ratio(
    characters: Sequence[RawCharCandidate],
    *,
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
    centre_factor: float = DEFAULT_CENTRE_DISTANCE_FACTOR,
    centre_cap: float = DEFAULT_CENTRE_DISTANCE_CAP_POINTS,
    size_similarity: float = DEFAULT_SIZE_SIMILARITY,
) -> float:
    """Geometry-first interleaved overprint ratio among retained glyphs.

    Legitimate repeats occupy distinct non-overlapping horizontal positions.
    Overprint doubles share near-identical centres / high IoU.
    """

    n = len(characters)
    if n < 2:
        return 0.0
    cell = max(centre_cap, 4.0)
    buckets: dict[tuple[str, int, int], list[int]] = defaultdict(list)
    meaningful = 0
    for i, ch in enumerate(characters):
        if ch.text.isspace() or not ch.text.isalnum():
            continue
        meaningful += 1
        cx, cy = _centre(ch)
        buckets[(_nfc(ch.text), int(cx // cell), int(cy // cell))].append(i)
    if meaningful == 0:
        return 0.0
    interleaved: set[int] = set()
    for key, indices in buckets.items():
        text, bx, by = key
        neighbours: list[int] = []
        for cell_dx in (-1, 0, 1):
            for cell_dy in (-1, 0, 1):
                neighbours.extend(buckets.get((text, bx + cell_dx, by + cell_dy), []))
        for i in indices:
            for j in neighbours:
                if j <= i:
                    continue
                a, b = characters[i], characters[j]
                if not _are_near_overprint_pair(
                    a,
                    b,
                    iou_threshold=iou_threshold,
                    centre_factor=centre_factor,
                    centre_cap=centre_cap,
                    size_similarity=size_similarity,
                ):
                    continue
                if (a.x1 <= b.x0 or b.x1 <= a.x0) and _iou(a, b) < 0.15:
                    continue
                interleaved.add(i)
                interleaved.add(j)
    return len(interleaved) / max(meaningful, 1)


def _cluster_offsets(
    pairs: list[tuple[int, int, float, float]],
    characters: list[RawCharCandidate],
    *,
    abs_tol: float,
    size_factor: float,
    top_k: int,
) -> tuple[float, float, int, float, float]:
    """Return (dom_dx, dom_dy, cluster_count, top_support, top_k_support)."""

    if not pairs:
        return 0.0, 0.0, 0, 0.0, 0.0
    sizes = [max(characters[a].size, characters[b].size, 1.0) for a, b, _, _ in pairs]
    sizes_sorted = sorted(sizes)
    median_size = sizes_sorted[len(sizes_sorted) // 2]
    tol = max(abs_tol, size_factor * median_size, 1e-6)
    bin_size = tol
    bins: dict[tuple[int, int], list[int]] = defaultdict(list)
    for idx, (_a, _b, dx, dy) in enumerate(pairs):
        bins[(round(dx / bin_size), round(dy / bin_size))].append(idx)
    keys = list(bins.keys())
    uf = _UnionFind(len(keys))
    key_index = {k: i for i, k in enumerate(keys)}
    for kx, ky in keys:
        i = key_index[(kx, ky)]
        for nx in (kx - 1, kx, kx + 1):
            for ny in (ky - 1, ky, ky + 1):
                if (nx, ny) == (kx, ky):
                    continue
                j = key_index.get((nx, ny))
                if j is None:
                    continue
                dx1 = kx * bin_size
                dy1 = ky * bin_size
                dx2 = nx * bin_size
                dy2 = ny * bin_size
                if abs(dx1 - dx2) <= tol * 1.01 and abs(dy1 - dy2) <= tol * 1.01:
                    uf.union(i, j)
    cluster_sizes: Counter[int] = Counter()
    cluster_sum: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for k, member_idxs in bins.items():
        root = uf.find(key_index[k])
        cluster_sizes[root] += len(member_idxs)
        for pi in member_idxs:
            _a, _b, dx, dy = pairs[pi]
            cluster_sum[root].append((dx, dy))
    ranked = cluster_sizes.most_common()
    cluster_count = len(ranked)
    total = max(len(pairs), 1)
    top_support = ranked[0][1] / total if ranked else 0.0
    top_k_n = sum(c for _, c in ranked[: max(1, top_k)])
    top_k_support = top_k_n / total
    top_root = ranked[0][0]
    pts = cluster_sum[top_root]
    dom_dx = sum(p[0] for p in pts) / max(len(pts), 1)
    dom_dy = sum(p[1] for p in pts) / max(len(pts), 1)
    return (
        float(dom_dx),
        float(dom_dy),
        cluster_count,
        max(0.0, min(1.0, top_support)),
        max(0.0, min(1.0, top_k_support)),
    )


def _line_region_stats(
    characters: list[RawCharCandidate],
    pairs: list[tuple[int, int, float, float]],
    participating: set[int],
    *,
    page_width: float,
    page_height: float,
    thr: CompositeThresholds,
) -> tuple[int, int, float, float]:
    """Return (duplicate_line_count, duplicate_region_count, v_span, h_span)."""

    if not pairs or not participating:
        return 0, 0, 0.0, 0.0
    matched_indices: set[int] = set()
    for a, b, _, _ in pairs:
        matched_indices.add(a)
        matched_indices.add(b)

    line_chars: dict[int, list[int]] = defaultdict(list)
    for i, ch in enumerate(characters):
        if ch.text.isspace():
            continue
        line_chars[round(ch.top / 4.0)].append(i)

    severe_lines: list[int] = []
    for line_key, idxs in sorted(line_chars.items()):
        n_line = len(idxs)
        matched = sum(1 for i in idxs if i in matched_indices)
        if n_line < thr.region_min_chars:
            continue
        ratio = matched / max(n_line, 1)
        if matched >= thr.region_min_matched and ratio >= thr.region_severe_ratio:
            severe_lines.append(line_key)

    duplicate_line_count = len(severe_lines)
    regions = 0
    prev: int | None = None
    for key in severe_lines:
        if prev is None or key - prev > 1:
            regions += 1
        prev = key
    duplicate_region_count = regions

    xs = [_centre(characters[i])[0] for i in participating]
    ys = [_centre(characters[i])[1] for i in participating]
    h_span = (max(xs) - min(xs)) / max(page_width, 1.0) if xs else 0.0
    v_span = (max(ys) - min(ys)) / max(page_height, 1.0) if ys else 0.0
    return (
        duplicate_line_count,
        duplicate_region_count,
        max(0.0, min(1.0, v_span)),
        max(0.0, min(1.0, h_span)),
    )


def _reading_order_indices(characters: list[RawCharCandidate], indices: list[int]) -> list[int]:
    return sorted(indices, key=lambda i: (characters[i].top, characters[i].x0, i))


def _complete_partition_layer_pairs(
    characters: list[RawCharCandidate],
    *,
    key_fn: Callable[[RawCharCandidate], Hashable],
    min_chars: int = 4,
) -> tuple[list[tuple[int, int, float, float]], float, float] | None:
    by_key: dict[object, list[int]] = defaultdict(list)
    for i, ch in enumerate(characters):
        if ch.text.isspace():
            continue
        by_key[key_fn(ch)].append(i)
    if len(by_key) < 2:
        return None

    ranked = sorted(by_key.items(), key=lambda item: -len(item[1]))
    (_ka, idx_a), (_kb, idx_b) = ranked[0], ranked[1]
    if len(idx_a) < min_chars or len(idx_b) < min_chars:
        return None
    coverage = min(len(idx_a), len(idx_b)) / max(len(idx_a), len(idx_b))
    if coverage < 0.90:
        return None

    ord_a = _reading_order_indices(characters, idx_a)
    ord_b = _reading_order_indices(characters, idx_b)
    n_pair = min(len(ord_a), len(ord_b))
    text_a = "".join(characters[i].text for i in ord_a[:n_pair])
    text_b = "".join(characters[i].text for i in ord_b[:n_pair])
    if _nfc(text_a) != _nfc(text_b):
        return None

    pairs: list[tuple[int, int, float, float]] = []
    dxs: list[float] = []
    dys: list[float] = []
    for ia, ib in zip(ord_a[:n_pair], ord_b[:n_pair], strict=True):
        ca, cb = characters[ia], characters[ib]
        if _nfc(ca.text) != _nfc(cb.text):
            return None
        cax, cay = _centre(ca)
        cbx, cby = _centre(cb)
        if ca.sequence_index <= cb.sequence_index:
            dx, dy = cbx - cax, cby - cay
            pairs.append((ia, ib, dx, dy))
        else:
            dx, dy = cax - cbx, cay - cby
            pairs.append((ib, ia, dx, dy))
        dxs.append(dx)
        dys.append(dy)

    dxs_sorted = sorted(dxs)
    dys_sorted = sorted(dys)
    mid = n_pair // 2
    return pairs, dxs_sorted[mid], dys_sorted[mid]


def _complete_font_layer_pairs(
    characters: list[RawCharCandidate],
) -> tuple[list[tuple[int, int, float, float]], float, float] | None:
    return _complete_partition_layer_pairs(characters, key_fn=_font_key)


def _complete_size_or_tag_layer_pairs(
    characters: list[RawCharCandidate],
) -> tuple[list[tuple[int, int, float, float]], float, float] | None:
    by_size = _complete_partition_layer_pairs(characters, key_fn=_size_bucket)
    if by_size is not None:
        return by_size
    tagged_vals = {ch.tagged for ch in characters if ch.tagged is not None}
    if True in tagged_vals and False in tagged_vals:
        return _complete_partition_layer_pairs(characters, key_fn=lambda ch: bool(ch.tagged))
    return None


def _empty_metrics(strict_duplicate_ratio: float) -> NearOverprintMetrics:
    return NearOverprintMetrics(
        strict_duplicate_ratio=max(0.0, min(1.0, strict_duplicate_ratio)),
        near_overprint_duplicate_ratio=0.0,
        duplicate_layer_count=1,
        dominant_duplicate_offset_x=0.0,
        dominant_duplicate_offset_y=0.0,
    )


def _span_stats(
    characters: list[RawCharCandidate],
    pairs: list[tuple[int, int, float, float]],
) -> tuple[int, int]:
    """Return (matched_word_span, matched_line_span) without using published text."""

    if not pairs:
        return 0, 0
    line_bins: set[int] = set()
    centres: list[tuple[float, float]] = []
    for a, b, _, _ in pairs:
        cax, cay = _centre(characters[a])
        cbx, cby = _centre(characters[b])
        centres.append(((cax + cbx) / 2.0, (cay + cby) / 2.0))
        line_bins.add(round(cay / 4.0))
        line_bins.add(round(cby / 4.0))
    centres.sort(key=lambda c: (c[1], c[0]))
    word_count = 0
    prev: tuple[float, float] | None = None
    for cx, cy in centres:
        if prev is None:
            word_count = 1
            prev = (cx, cy)
            continue
        px, py = prev
        if abs(cy - py) > 3.0 or (cx - px) > 8.0:
            word_count += 1
        prev = (cx, cy)
    return word_count, len(line_bins)


def _layer_coverage_and_redundant(
    characters: list[RawCharCandidate],
    pairs: list[tuple[int, int, float, float]],
    participating: set[int],
) -> tuple[float, set[int], int]:
    """Return (coverage_ratio, redundant_indices, layer_count)."""

    if not pairs:
        return 0.0, set(), 1

    redundant: set[int] = set()
    for _a, b, _, _ in pairs:
        redundant.add(b)

    by_font: dict[str, set[int]] = defaultdict(set)
    for i in participating:
        by_font[_font_key(characters[i])].add(i)
    ranked = sorted(by_font.values(), key=len, reverse=True)
    if len(ranked) >= 2:
        smaller = ranked[1]
        larger = ranked[0]
        matched_smaller = {i for i in smaller if any(i in (a, b) for a, b, _, _ in pairs)}
        coverage = len(matched_smaller) / max(len(smaller), 1)
        if smaller and larger and coverage >= 0.5:
            redundant = set(smaller) & participating
        layer_count = min(len(ranked), 3)
    else:
        second = redundant
        first = participating - redundant
        smaller_size = min(len(first), len(second)) if first and second else len(second)
        matched_small = len(second) if len(second) <= len(first) else len(first)
        coverage = matched_small / max(smaller_size, 1) if smaller_size else 0.0
        layer_count = 2 if len(participating) >= 4 else 1

    return max(0.0, min(1.0, coverage)), redundant, layer_count


def _replace_metrics(
    base: NearOverprintMetrics,
    *,
    composite: bool | None = None,
    hard_rule_path: str | None = None,
    hard_rule_explanation: tuple[str, ...] | None = None,
    duplicate_layer_evidence: object | None = None,
) -> NearOverprintMetrics:
    return NearOverprintMetrics(
        strict_duplicate_ratio=base.strict_duplicate_ratio,
        near_overprint_duplicate_ratio=base.near_overprint_duplicate_ratio,
        duplicate_layer_count=base.duplicate_layer_count,
        dominant_duplicate_offset_x=base.dominant_duplicate_offset_x,
        dominant_duplicate_offset_y=base.dominant_duplicate_offset_y,
        duplicate_layer_coverage_ratio=base.duplicate_layer_coverage_ratio,
        matched_near_duplicate_count=base.matched_near_duplicate_count,
        dominant_offset_support_ratio=base.dominant_offset_support_ratio,
        matched_word_span=base.matched_word_span,
        matched_line_span=base.matched_line_span,
        composite_duplicate_layer_evidence=(
            base.composite_duplicate_layer_evidence if composite is None else composite
        ),
        top_offset_cluster_support_ratio=base.top_offset_cluster_support_ratio,
        top_k_offset_cluster_support_ratio=base.top_k_offset_cluster_support_ratio,
        offset_cluster_count=base.offset_cluster_count,
        duplicate_line_count=base.duplicate_line_count,
        duplicate_region_count=base.duplicate_region_count,
        page_vertical_span_ratio=base.page_vertical_span_ratio,
        page_horizontal_span_ratio=base.page_horizontal_span_ratio,
        hard_rule_path=base.hard_rule_path if hard_rule_path is None else hard_rule_path,
        hard_rule_explanation=(
            base.hard_rule_explanation if hard_rule_explanation is None else hard_rule_explanation
        ),
        duplicate_layer_evidence=(
            base.duplicate_layer_evidence
            if duplicate_layer_evidence is None
            else duplicate_layer_evidence
        ),
    )


def analyse_and_clean_near_overprint(
    characters: list[RawCharCandidate],
    *,
    strict_duplicate_ratio: float,
    words: list[RawWordCandidate],
    thresholds: CompositeThresholds | None = None,
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
    centre_factor: float = DEFAULT_CENTRE_DISTANCE_FACTOR,
    centre_cap: float = DEFAULT_CENTRE_DISTANCE_CAP_POINTS,
    size_similarity: float = DEFAULT_SIZE_SIMILARITY,
    offset_bin: float = DEFAULT_OFFSET_BIN_POINTS,
    page_width: float = 612.0,
    page_height: float = 792.0,
) -> NearOverprintOutcome:
    """Detect near-overprints; clean (PATH C) or hard-reject when PATH A/B fire."""

    thr = thresholds or CompositeThresholds()
    n = len(characters)
    empty = _empty_metrics(strict_duplicate_ratio)
    if n < 2:
        return NearOverprintOutcome(
            metrics=empty, selection="none", characters=characters, words=words
        )

    cell = max(centre_cap, 4.0)
    buckets: dict[tuple[str, int, int], list[int]] = defaultdict(list)
    for i, ch in enumerate(characters):
        if ch.text.isspace():
            continue
        cx, cy = _centre(ch)
        buckets[(_nfc(ch.text), int(cx // cell), int(cy // cell))].append(i)

    pairs: list[tuple[int, int, float, float]] = []
    uf = _UnionFind(n)
    seen_pair: set[tuple[int, int]] = set()

    def _consider(i: int, j: int) -> None:
        if i == j:
            return
        a, b = (i, j) if i < j else (j, i)
        if (a, b) in seen_pair:
            return
        seen_pair.add((a, b))
        ca, cb = characters[a], characters[b]
        if not _are_near_overprint_pair(
            ca,
            cb,
            iou_threshold=iou_threshold,
            centre_factor=centre_factor,
            centre_cap=centre_cap,
            size_similarity=size_similarity,
        ):
            return
        cax, cay = _centre(ca)
        cbx, cby = _centre(cb)
        if ca.sequence_index <= cb.sequence_index:
            dx, dy = cbx - cax, cby - cay
            pairs.append((a, b, dx, dy))
        else:
            dx, dy = cax - cbx, cay - cby
            pairs.append((b, a, dx, dy))
        uf.union(a, b)

    for key, indices in buckets.items():
        text, bx, by = key
        neighbours: list[int] = []
        for cell_dx in (-1, 0, 1):
            for cell_dy in (-1, 0, 1):
                neighbours.extend(buckets.get((text, bx + cell_dx, by + cell_dy), []))
        for i in indices:
            for j in neighbours:
                if j > i:
                    _consider(i, j)

    reading = [
        i
        for i, ch in sorted(
            enumerate(characters), key=lambda item: (item[1].top, item[1].x0, item[0])
        )
        if not ch.text.isspace()
    ]
    for pos in range(len(reading) - 1):
        i, j = reading[pos], reading[pos + 1]
        if _nfc(characters[i].text) != _nfc(characters[j].text):
            continue
        _consider(i, j)

    font_layer = _complete_font_layer_pairs(characters)
    if font_layer is None:
        font_layer = _complete_size_or_tag_layer_pairs(characters)
    if font_layer is not None:
        font_pairs, _med_dx, _med_dy = font_layer
        for a, b, dx, dy in font_pairs:
            aa, bb = (a, b) if a < b else (b, a)
            if (aa, bb) not in seen_pair:
                seen_pair.add((aa, bb))
                pairs.append((a, b, dx, dy))
                uf.union(a, b)

    if not pairs:
        return NearOverprintOutcome(
            metrics=empty, selection="none", characters=characters, words=words
        )

    participating: set[int] = set()
    for a, b, _, _ in pairs:
        participating.add(a)
        participating.add(b)

    offset_counts: Counter[tuple[float, float]] = Counter()
    for _, _, dx, dy in pairs:
        offset_counts[_bin_offset(dx, dy, offset_bin)] += 1
    (_exact_dx, _exact_dy), exact_count = offset_counts.most_common(1)[0]
    exact_support = exact_count / max(len(pairs), 1)

    dom_dx, dom_dy, cluster_count, top_support, top_k_support = _cluster_offsets(
        pairs,
        characters,
        abs_tol=thr.offset_cluster_abs_tol,
        size_factor=thr.offset_cluster_size_factor,
        top_k=thr.offset_cluster_top_k,
    )
    if font_layer is not None:
        dom_dx, dom_dy = font_layer[1], font_layer[2]
        dominant_support = 1.0
        top_support = 1.0
        top_k_support = 1.0
    else:
        dominant_support = exact_support

    coverage, redundant, layer_count = _layer_coverage_and_redundant(
        characters, pairs, participating
    )
    near_ratio = len(redundant) / max(n, 1)
    word_span, line_span = _span_stats(characters, pairs)
    dup_lines, dup_regions, v_span, h_span = _line_region_stats(
        characters,
        pairs,
        participating,
        page_width=page_width,
        page_height=page_height,
        thr=thr,
    )

    metrics = NearOverprintMetrics(
        strict_duplicate_ratio=max(0.0, min(1.0, strict_duplicate_ratio)),
        near_overprint_duplicate_ratio=max(0.0, min(1.0, near_ratio)),
        duplicate_layer_count=layer_count,
        dominant_duplicate_offset_x=float(dom_dx),
        dominant_duplicate_offset_y=float(dom_dy),
        duplicate_layer_coverage_ratio=coverage,
        matched_near_duplicate_count=len(pairs),
        dominant_offset_support_ratio=max(0.0, min(1.0, dominant_support)),
        matched_word_span=word_span,
        matched_line_span=line_span,
        composite_duplicate_layer_evidence=False,
        top_offset_cluster_support_ratio=top_support,
        top_k_offset_cluster_support_ratio=top_k_support,
        offset_cluster_count=cluster_count,
        duplicate_line_count=dup_lines,
        duplicate_region_count=dup_regions,
        page_vertical_span_ratio=v_span,
        page_horizontal_span_ratio=h_span,
    )
    evidence = build_duplicate_layer_evidence(metrics, thr)
    composite = evidence.hard_rejection
    hard_path = evidence.selected_path
    explanation = evidence_to_explanation(evidence)
    metrics = _replace_metrics(
        metrics,
        composite=composite,
        hard_rule_path=hard_path,
        hard_rule_explanation=explanation.format_lines(),
        duplicate_layer_evidence=evidence,
    )

    if not composite:
        return NearOverprintOutcome(
            metrics=metrics, selection="none", characters=characters, words=words
        )

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)
    duplicate_groups = [g for g in groups.values() if len(g) >= 2]
    if not duplicate_groups:
        return NearOverprintOutcome(metrics=metrics, selection="ambiguous", characters=[], words=[])

    layer_members: dict[tuple[str, int, bool | None], set[int]] = defaultdict(set)
    for group in duplicate_groups:
        for idx in group:
            layer_members[_layer_signature(characters[idx])].add(idx)

    if len(layer_members) < 2:
        return _select_by_offset_or_ambiguous(
            characters,
            words,
            pairs=pairs,
            metrics=metrics,
            participating=participating,
            duplicate_groups=duplicate_groups,
            redundant=redundant,
            dom_dx=dom_dx,
            dom_dy=dom_dy,
            thr=thr,
            cluster_tol=max(thr.offset_cluster_abs_tol, thr.offset_cluster_size_factor * 12.0),
        )

    scored: list[tuple[float, tuple[str, int, bool | None], set[int]]] = []
    for sig, members in layer_members.items():
        coverage_n = len(members)
        fonts = {_font_key(characters[i]) for i in members}
        font_consistency = 1.0 if len(fonts) == 1 else 0.5
        tagged_vals = {characters[i].tagged for i in members}
        tagged_bonus = 0.02 if True in tagged_vals and False not in tagged_vals else 0.0
        score = coverage_n * font_consistency + tagged_bonus * coverage_n
        scored.append((score, sig, members))
    scored.sort(key=lambda t: (-t[0], t[1][0], t[1][1]))

    if len(scored) >= 3:
        top_coverages = [len(m) for _, _, m in scored[:3]]
        if min(top_coverages) >= 0.7 * max(top_coverages):
            return NearOverprintOutcome(
                metrics=metrics, selection="ambiguous", characters=[], words=[]
            )

    _winner_score, _winner_sig, winner_members = scored[0]
    _loser_score, _, loser_members = scored[1]
    winner_cov = len(winner_members)
    loser_cov = len(loser_members)
    if winner_cov == 0:
        return NearOverprintOutcome(metrics=metrics, selection="ambiguous", characters=[], words=[])
    coverage_gap = abs(winner_cov - loser_cov) / max(winner_cov, loser_cov)
    pair_set = {(a, b) for a, b, _, _ in pairs} | {(b, a) for a, b, _, _ in pairs}
    loser_paired = sum(
        1 for li in loser_members if any((li, wi) in pair_set for wi in winner_members)
    )
    cross = loser_paired / max(loser_cov, 1)
    conflict = any(len({_nfc(characters[i].text) for i in g}) > 1 for g in duplicate_groups)
    safe = (
        not conflict
        and cross >= DEFAULT_CROSS_COVERAGE_MIN
        and (
            coverage_gap <= DEFAULT_COVERAGE_GAP_MAX or (winner_cov >= loser_cov and cross >= 0.90)
        )
    )
    if not safe:
        return NearOverprintOutcome(metrics=metrics, selection="ambiguous", characters=[], words=[])

    keep: set[int] = set()
    for i in range(n):
        if i not in participating:
            keep.add(i)
    for group in duplicate_groups:
        winners_in_group = [i for i in group if i in winner_members]
        if winners_in_group:
            keep.add(min(winners_in_group, key=lambda i: characters[i].sequence_index))
        else:
            keep.add(min(group, key=lambda i: characters[i].sequence_index))

    return _finish_clean(characters, keep, metrics=metrics, thr=thr)


def _word_looks_overprint_garbled(text: str) -> bool:
    """True when a single word still looks like an AABB near-overprint band.

    ``bookkeeper`` has three consecutive legitimate doubles (``ookkee``) but is
    short; residual header/footer bands are long with dense AABB runs.
    """

    if not text or len(text) < 6:
        return False
    run = max_consecutive_double_pair_run(text)
    if run >= _MIN_AABB_RUN_FOR_REJECT:
        return True
    return run >= 3 and len(text) >= 16 and interleaved_double_ratio(text) >= 0.30


def _strip_garbled_overprint_words(
    characters: list[RawCharCandidate],
) -> list[RawCharCandidate]:
    """Drop residual AABB-corrupted words (regional header/footer salvage)."""

    words = rebuild_words_from_characters(characters)
    drop: set[int] = set()
    for word in words:
        if _word_looks_overprint_garbled(word.text):
            drop.update(word.char_indices)
    if not drop:
        return characters
    kept = [ch for i, ch in enumerate(characters) if i not in drop]
    return _renumber_characters(kept)


def _finish_clean(
    characters: list[RawCharCandidate],
    keep: set[int],
    *,
    metrics: NearOverprintMetrics,
    thr: CompositeThresholds,
) -> NearOverprintOutcome:
    cleaned = _renumber_characters([characters[i] for i in sorted(keep)])
    # Regional PATH B salvage: imperfect pairing can leave AABB header/footer
    # bands while the body is already single-copy — strip those words first.
    cleaned = _strip_garbled_overprint_words(cleaned)
    if not cleaned:
        return NearOverprintOutcome(metrics=metrics, selection="ambiguous", characters=[], words=[])
    new_words = rebuild_words_from_characters(cleaned)
    provisional = " ".join(w.text for w in new_words)
    if interleaved_double_ratio(provisional) >= 0.35:
        return NearOverprintOutcome(metrics=metrics, selection="ambiguous", characters=[], words=[])
    if max_consecutive_double_pair_run(provisional) >= _MIN_AABB_RUN_FOR_REJECT:
        return NearOverprintOutcome(metrics=metrics, selection="ambiguous", characters=[], words=[])
    if geometric_interleave_ratio(cleaned) >= DEFAULT_GEOMETRIC_INTERLEAVE_RATIO:
        return NearOverprintOutcome(metrics=metrics, selection="ambiguous", characters=[], words=[])
    residual = _quick_redundant_ratio(
        cleaned,
        thr=thr,
        iou_threshold=DEFAULT_IOU_THRESHOLD,
        centre_factor=DEFAULT_CENTRE_DISTANCE_FACTOR,
        centre_cap=DEFAULT_CENTRE_DISTANCE_CAP_POINTS,
        size_similarity=DEFAULT_SIZE_SIMILARITY,
    )
    # Any residual above the hard near-overprint floor is unsafe to publish.
    if residual > thr.max_near_overprint_ratio:
        return NearOverprintOutcome(metrics=metrics, selection="ambiguous", characters=[], words=[])
    # PATH A/B pages must clean to near-zero residual / dense AABB; otherwise
    # prefer visual_authority over publishing garbled cross-font merges.
    if metrics.hard_rule_path in {"A", "B"} or metrics.near_overprint_duplicate_ratio > 0.25:
        if residual > 0.02 or geometric_interleave_ratio(cleaned) > 0.02:
            return NearOverprintOutcome(
                metrics=metrics, selection="ambiguous", characters=[], words=[]
            )
        if max_consecutive_double_pair_run(provisional) >= _MIN_AABB_RUN_FOR_REJECT:
            return NearOverprintOutcome(
                metrics=metrics, selection="ambiguous", characters=[], words=[]
            )
    return NearOverprintOutcome(
        metrics=metrics, selection="cleaned", characters=cleaned, words=new_words
    )


def _quick_redundant_ratio(
    characters: list[RawCharCandidate],
    *,
    thr: CompositeThresholds,
    iou_threshold: float,
    centre_factor: float,
    centre_cap: float,
    size_similarity: float,
) -> float:
    n = len(characters)
    if n < 2:
        return 0.0
    cell = max(centre_cap, 4.0)
    buckets: dict[tuple[str, int, int], list[int]] = defaultdict(list)
    for i, ch in enumerate(characters):
        if ch.text.isspace():
            continue
        cx, cy = _centre(ch)
        buckets[(_nfc(ch.text), int(cx // cell), int(cy // cell))].append(i)
    redundant: set[int] = set()
    for key, indices in buckets.items():
        text, bx, by = key
        neighbours: list[int] = []
        for cell_dx in (-1, 0, 1):
            for cell_dy in (-1, 0, 1):
                neighbours.extend(buckets.get((text, bx + cell_dx, by + cell_dy), []))
        for i in indices:
            for j in neighbours:
                if j <= i:
                    continue
                if _are_near_overprint_pair(
                    characters[i],
                    characters[j],
                    iou_threshold=iou_threshold,
                    centre_factor=centre_factor,
                    centre_cap=centre_cap,
                    size_similarity=size_similarity,
                ):
                    later = j if characters[i].sequence_index <= characters[j].sequence_index else i
                    redundant.add(later)
    _ = thr
    return len(redundant) / max(n, 1)


def _select_by_offset_or_ambiguous(
    characters: list[RawCharCandidate],
    words: list[RawWordCandidate],
    *,
    pairs: list[tuple[int, int, float, float]],
    metrics: NearOverprintMetrics,
    participating: set[int],
    duplicate_groups: list[list[int]],
    redundant: set[int],
    dom_dx: float,
    dom_dy: float,
    thr: CompositeThresholds,
    cluster_tol: float,
) -> NearOverprintOutcome:
    _ = words
    if abs(dom_dx) < 1e-6 and abs(dom_dy) < 1e-6:
        keep: set[int] = set(range(len(characters))) - participating
        for group in duplicate_groups:
            keep.add(min(group, key=lambda i: characters[i].sequence_index))
        return _finish_clean(characters, keep, metrics=metrics, thr=thr)

    keep_set: set[int] = set(range(len(characters)))
    drop: set[int] = set(redundant)
    for a, b, dx, dy in pairs:
        if abs(dx - dom_dx) <= cluster_tol and abs(dy - dom_dy) <= cluster_tol:
            drop.add(a)
            keep_set.add(b)
    keep_set -= drop
    for i in range(len(characters)):
        if i not in participating:
            keep_set.add(i)

    if not keep_set or len(keep_set) >= len(characters) * 0.95:
        return NearOverprintOutcome(metrics=metrics, selection="ambiguous", characters=[], words=[])
    return _finish_clean(characters, keep_set, metrics=metrics, thr=thr)

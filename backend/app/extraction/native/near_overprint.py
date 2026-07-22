"""Near-overprint duplicate detection, composite hard evidence, and layer collapse.

Phase 3.4: soft duplication_score alone must not accept interleaved doubles.
Composite layer evidence forces clean-or-reject.
"""

from __future__ import annotations

import math
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Literal

from backend.app.extraction.native.models import RawCharCandidate, RawWordCandidate

DEFAULT_IOU_THRESHOLD = 0.35
DEFAULT_CENTRE_DISTANCE_FACTOR = 0.35
DEFAULT_CENTRE_DISTANCE_CAP_POINTS = 3.5
DEFAULT_SIZE_SIMILARITY = 0.40
DEFAULT_OFFSET_BIN_POINTS = 0.25
DEFAULT_MIN_PAIR_FRACTION_FOR_LAYER = 0.15
DEFAULT_CROSS_COVERAGE_MIN = 0.85
DEFAULT_COVERAGE_GAP_MAX = 0.05
DEFAULT_MIN_WORD_SPAN = 3
DEFAULT_MIN_LINE_SPAN = 2


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
    min_dominant_offset_support_ratio: float = 0.55
    min_word_span: int = DEFAULT_MIN_WORD_SPAN
    min_line_span: int = DEFAULT_MIN_LINE_SPAN


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


def composite_duplicate_layer_evidence(
    metrics: NearOverprintMetrics,
    thresholds: CompositeThresholds,
) -> bool:
    """True when generic evidence shows a substantial duplicated layer."""

    span_ok = (
        metrics.matched_word_span >= thresholds.min_word_span
        or metrics.matched_line_span >= thresholds.min_line_span
        # Complete near-full layer duplicates may sit on one line.
        or (
            metrics.duplicate_layer_coverage_ratio >= 0.90
            and metrics.matched_near_duplicate_count >= 8
        )
    )
    min_matches = thresholds.min_near_duplicate_match_count
    if (
        metrics.duplicate_layer_coverage_ratio >= 0.90
        and metrics.dominant_offset_support_ratio >= 0.90
        and metrics.duplicate_layer_count >= 2
    ):
        # Complete cross-layer duplicates can be short pages/lines.
        min_matches = min(min_matches, 8)
    return (
        metrics.matched_near_duplicate_count >= min_matches
        and metrics.near_overprint_duplicate_ratio > thresholds.max_near_overprint_ratio
        and metrics.duplicate_layer_coverage_ratio > thresholds.max_duplicate_layer_coverage_ratio
        and metrics.dominant_offset_support_ratio >= thresholds.min_dominant_offset_support_ratio
        and span_ok
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
    # Approximate words by clustering pair centres with x-gap.
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

    # Redundant = later-painted glyph in each pair (removable overprint side).
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
        # Prefer redundant = members of the smaller/later layer when fonts differ.
        if smaller and larger and coverage >= 0.5:
            # Keep larger as primary; smaller as redundant when largely paired.
            redundant = set(smaller) & participating
        layer_count = min(len(ranked), 3)
    else:
        # Same-font: coverage = paired / participating.
        coverage = len(participating) / max(len(participating), 1)
        # For same-font doubles, each pair removes one → coverage of "second" layer ≈ 1.
        second = redundant
        first = participating - redundant
        smaller_size = min(len(first), len(second)) if first and second else len(second)
        matched_small = len(second) if len(second) <= len(first) else len(first)
        coverage = matched_small / max(smaller_size, 1) if smaller_size else 0.0
        layer_count = 2 if len(participating) >= 4 else 1

    return max(0.0, min(1.0, coverage)), redundant, layer_count


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
) -> NearOverprintOutcome:
    """Detect near-overprints; clean or hard-reject when composite evidence is true."""

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
    (dom_dx, dom_dy), dom_count = offset_counts.most_common(1)[0]
    if font_layer is not None:
        dom_dx, dom_dy = font_layer[1], font_layer[2]
        dominant_support = 1.0
    else:
        dominant_support = dom_count / max(len(pairs), 1)

    coverage, redundant, layer_count = _layer_coverage_and_redundant(
        characters, pairs, participating
    )
    # Redundant ratio: removable overprint chars / total.
    near_ratio = len(redundant) / max(n, 1)
    word_span, line_span = _span_stats(characters, pairs)

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
    )
    composite = composite_duplicate_layer_evidence(metrics, thr)
    metrics = NearOverprintMetrics(
        strict_duplicate_ratio=metrics.strict_duplicate_ratio,
        near_overprint_duplicate_ratio=metrics.near_overprint_duplicate_ratio,
        duplicate_layer_count=metrics.duplicate_layer_count,
        dominant_duplicate_offset_x=metrics.dominant_duplicate_offset_x,
        dominant_duplicate_offset_y=metrics.dominant_duplicate_offset_y,
        duplicate_layer_coverage_ratio=metrics.duplicate_layer_coverage_ratio,
        matched_near_duplicate_count=metrics.matched_near_duplicate_count,
        dominant_offset_support_ratio=metrics.dominant_offset_support_ratio,
        matched_word_span=metrics.matched_word_span,
        matched_line_span=metrics.matched_line_span,
        composite_duplicate_layer_evidence=composite,
    )

    if not composite:
        # Soft diagnostics only — leave text (legitimate shadow / sparse pairs).
        return NearOverprintOutcome(
            metrics=metrics, selection="none", characters=characters, words=words
        )

    # Composite evidence: must clean or reject — never publish doubles.
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


def _finish_clean(
    characters: list[RawCharCandidate],
    keep: set[int],
    *,
    metrics: NearOverprintMetrics,
    thr: CompositeThresholds,
) -> NearOverprintOutcome:
    cleaned = _renumber_characters([characters[i] for i in sorted(keep)])
    new_words = rebuild_words_from_characters(cleaned)
    provisional = " ".join(w.text for w in new_words)
    if interleaved_double_ratio(provisional) >= 0.35:
        return NearOverprintOutcome(metrics=metrics, selection="ambiguous", characters=[], words=[])
    residual = _quick_redundant_ratio(
        cleaned,
        thr=thr,
        iou_threshold=DEFAULT_IOU_THRESHOLD,
        centre_factor=DEFAULT_CENTRE_DISTANCE_FACTOR,
        centre_cap=DEFAULT_CENTRE_DISTANCE_CAP_POINTS,
        size_similarity=DEFAULT_SIZE_SIMILARITY,
    )
    if residual > thr.max_near_overprint_ratio and residual > 0.15:
        return NearOverprintOutcome(metrics=metrics, selection="ambiguous", characters=[], words=[])
    # Keep pre-clean diagnostics for UI; cleaned selection tells trust not to hard-reject.
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
    # silence unused thr
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
) -> NearOverprintOutcome:
    _ = words
    if abs(dom_dx) < 1e-6 and abs(dom_dy) < 1e-6:
        keep: set[int] = set(range(len(characters))) - participating
        for group in duplicate_groups:
            keep.add(min(group, key=lambda i: characters[i].sequence_index))
        return _finish_clean(characters, keep, metrics=metrics, thr=thr)

    keep_set: set[int] = set(range(len(characters)))
    drop: set[int] = set(redundant)
    bin_eps = DEFAULT_OFFSET_BIN_POINTS
    for a, b, dx, dy in pairs:
        if abs(dx - dom_dx) <= bin_eps * 1.5 and abs(dy - dom_dy) <= bin_eps * 1.5:
            drop.add(a)
            keep_set.add(b)
    keep_set -= drop
    for i in range(len(characters)):
        if i not in participating:
            keep_set.add(i)

    if not keep_set or len(keep_set) >= len(characters) * 0.95:
        return NearOverprintOutcome(metrics=metrics, selection="ambiguous", characters=[], words=[])
    return _finish_clean(characters, keep_set, metrics=metrics, thr=thr)

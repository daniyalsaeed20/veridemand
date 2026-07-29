"""Deterministic failed-region clustering for targeted repair."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from backend.app.contracts.geometry import NormalisedBoundingBox
from backend.app.contracts.native import NativeWord
from backend.app.contracts.repair import (
    REPAIR_POLICY_VERSION,
    RepairMethod,
    RepairRegionRecord,
)
from backend.app.extraction.routing.models import RoutingPolicy


@dataclass(slots=True)
class _Cluster:
    word_indices: list[int]
    word_ids: list[str]
    x0: float
    y0: float
    x1: float
    y1: float
    reason_codes: set[str]
    page_band: str  # header | body | footer


def _clamp01(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, value))


def _page_band(y_centre: float) -> str:
    if y_centre < 0.18:
        return "header"
    if y_centre > 0.82:
        return "footer"
    return "body"


def _valid_bbox(bbox: NormalisedBoundingBox) -> bool:
    try:
        if not all(math.isfinite(v) for v in (bbox.x, bbox.y, bbox.width, bbox.height)):
            return False
        if bbox.width <= 0 or bbox.height <= 0:
            return False
        return not (bbox.x + bbox.width > 1.0 + 1e-9 or bbox.y + bbox.height > 1.0 + 1e-9)
    except (TypeError, ValueError):
        return False


def _v_overlap_ratio(a0: float, a1: float, b0: float, b1: float) -> float:
    overlap = max(0.0, min(a1, b1) - max(a0, b0))
    height = max(1e-9, min(a1 - a0, b1 - b0))
    return overlap / height


def _same_line(
    ay0: float,
    ay1: float,
    by0: float,
    by1: float,
    *,
    min_overlap: float,
) -> bool:
    return _v_overlap_ratio(ay0, ay1, by0, by1) >= min_overlap


def expand_bbox(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    padding_ratio: float,
) -> NormalisedBoundingBox:
    width = max(0.0, x1 - x0)
    height = max(0.0, y1 - y0)
    pad_x = width * padding_ratio
    pad_y = height * padding_ratio
    nx0 = _clamp01(x0 - pad_x)
    ny0 = _clamp01(y0 - pad_y)
    nx1 = _clamp01(x1 + pad_x)
    ny1 = _clamp01(y1 + pad_y)
    if nx1 <= nx0 or ny1 <= ny0:
        raise ValueError("Expanded repair region has non-positive area.")
    return NormalisedBoundingBox(x=nx0, y=ny0, width=nx1 - nx0, height=ny1 - ny0)


def cluster_failed_boxes(
    words: Sequence[NativeWord],
    failed_indices: Sequence[int],
    *,
    page_number: int,
    policy: RoutingPolicy,
    failure_reason_codes: Sequence[str] | None = None,
    default_method: RepairMethod = RepairMethod.RECOGNITION_ONLY,
) -> list[RepairRegionRecord]:
    """Cluster nearby failed boxes into bounded repair regions.

    Uses geometric proximity, line membership, vertical overlap, horizontal gap,
    shared verification failure, and page-region boundaries. Distant failures
    remain separate; characters are never one-crop-each.
    """

    gap = policy.repair_cluster_gap
    line_overlap = policy.repair_line_v_overlap
    reasons = list(failure_reason_codes or ["verification_failed"])
    items: list[tuple[int, NativeWord, float, float, float, float]] = []
    for i in failed_indices:
        if not (0 <= i < len(words)):
            continue
        word = words[i]
        if word.geometry is None or not _valid_bbox(word.geometry.bbox):
            continue
        bbox = word.geometry.bbox
        items.append(
            (
                i,
                word,
                float(bbox.x),
                float(bbox.y),
                float(bbox.x + bbox.width),
                float(bbox.y + bbox.height),
            )
        )
    items.sort(key=lambda t: (t[3], t[2], t[0]))

    clusters: list[_Cluster] = []
    for idx, word, wx0, wy0, wx1, wy1 in items:
        band = _page_band((wy0 + wy1) / 2.0)
        placed = False
        for cluster in clusters:
            # Do not merge across distant page bands unless overlapping.
            if cluster.page_band != band and not (
                wy0 <= cluster.y1 + gap and wy1 >= cluster.y0 - gap
            ):
                continue
            same_line = _same_line(wy0, wy1, cluster.y0, cluster.y1, min_overlap=line_overlap)
            nearby = (
                wx0 <= cluster.x1 + gap
                and wx1 >= cluster.x0 - gap
                and wy0 <= cluster.y1 + gap
                and wy1 >= cluster.y0 - gap
            )
            # Prefer line-aware merge; otherwise proximity with shared failure.
            if same_line:
                h_gap = max(0.0, max(wx0, cluster.x0) - min(wx1, cluster.x1))
                median_w = max((wx1 - wx0 + cluster.x1 - cluster.x0) / 2.0, 1e-4)
                if h_gap > median_w * 3.0 + gap:
                    continue
                nearby = True
            if not nearby:
                continue
            cluster.word_indices.append(idx)
            cluster.word_ids.append(word.id)
            cluster.x0 = min(cluster.x0, wx0)
            cluster.y0 = min(cluster.y0, wy0)
            cluster.x1 = max(cluster.x1, wx1)
            cluster.y1 = max(cluster.y1, wy1)
            cluster.reason_codes.update(reasons)
            placed = True
            break
        if not placed:
            clusters.append(
                _Cluster(
                    word_indices=[idx],
                    word_ids=[word.id],
                    x0=wx0,
                    y0=wy0,
                    x1=wx1,
                    y1=wy1,
                    reason_codes=set(reasons),
                    page_band=band,
                )
            )

    records: list[RepairRegionRecord] = []
    for i, cluster in enumerate(clusters):
        width = cluster.x1 - cluster.x0
        height = cluster.y1 - cluster.y0
        if width <= 0 or height <= 0 or not math.isfinite(width) or not math.isfinite(height):
            continue
        normalised = NormalisedBoundingBox(
            x=_clamp01(cluster.x0),
            y=_clamp01(cluster.y0),
            width=_clamp01(width),
            height=_clamp01(height),
        )
        # Re-validate after clamp.
        if normalised.width <= 0 or normalised.height <= 0:
            continue
        try:
            expanded = expand_bbox(
                cluster.x0,
                cluster.y0,
                cluster.x1,
                cluster.y1,
                padding_ratio=policy.repair_padding_ratio,
            )
        except ValueError:
            continue
        coverage = float(expanded.width * expanded.height)
        records.append(
            RepairRegionRecord(
                repair_region_id=f"repair_p{page_number:04d}_{i + 1:03d}",
                page_number=page_number,
                source_word_ids=list(cluster.word_ids),
                normalised_bbox=normalised,
                expanded_normalised_bbox=expanded,
                page_coverage_ratio=round(min(1.0, coverage), 6),
                failure_reason_codes=sorted(cluster.reason_codes),
                repair_method=default_method,
                policy_version=policy.repair_policy_version or REPAIR_POLICY_VERSION,
            )
        )
    return records

"""Dual-detector geometric merge for Phase 5 Task C1 shadow calibration.

Algorithm version: ``phase5-dual-detector-merge-v1``.

Deterministic union of mobile + server detections that:
- merges exact duplicates and high-IoU equivalents;
- preserves detector provenance and both confidences;
- emits stable merged region IDs;
- keeps neighbouring non-overlapping lines separate;
- retains fragmented detections for coverage analysis;
- does not discard a handwriting-relevant smaller box merely because the
  second detector produced a larger overlapping box (prefer the tighter
  box when containment is mutual/high; otherwise keep both as fragments).
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

from backend.app.contracts.geometry import NormalisedBoundingBox
from backend.app.datasets.phase5.constants import (
    DETECTOR_DUAL_MERGE_VERSION,
    DETECTOR_MERGE_EQUIVALENT_IOU,
    DETECTOR_MERGE_NEIGHBOUR_IOU,
)
from backend.app.datasets.phase5.geometry_match import (
    bbox_from_tuple,
    bbox_iou,
    containment_ratio,
)
from backend.app.extraction.visual.detect_first_types import DetectedTextRegion


def _bbox(region: DetectedTextRegion) -> NormalisedBoundingBox:
    return bbox_from_tuple(region.bbox_norm)


def _area(bbox: NormalisedBoundingBox) -> float:
    return float(bbox.width * bbox.height)


def _stable_merged_id(
    *,
    page_index: int,
    polygon_norm: tuple[tuple[float, float], ...],
    source_names: tuple[str, ...],
) -> str:
    digest = hashlib.sha256()
    digest.update(f"{DETECTOR_DUAL_MERGE_VERSION}:{page_index}:".encode())
    digest.update("|".join(sorted(source_names)).encode())
    digest.update(b":")
    for x, y in polygon_norm:
        digest.update(f"{x:.6f},{y:.6f};".encode())
    return f"dfmrg_{digest.hexdigest()[:16]}"


def _are_equivalent(
    a: DetectedTextRegion,
    b: DetectedTextRegion,
    *,
    equivalent_iou: float,
) -> bool:
    ba, bb = _bbox(a), _bbox(b)
    iou = bbox_iou(ba, bb)
    if iou >= equivalent_iou:
        return True
    # Near-exact coordinate match (same crop after pad).
    return (
        abs(ba.x - bb.x) < 1e-4
        and abs(ba.y - bb.y) < 1e-4
        and abs(ba.width - bb.width) < 1e-4
        and abs(ba.height - bb.height) < 1e-4
    )


def _prefer_region(a: DetectedTextRegion, b: DetectedTextRegion) -> DetectedTextRegion:
    """Choose geometry when two detectors agree: prefer tighter, then higher conf."""

    ba, bb = _bbox(a), _bbox(b)
    area_a, area_b = _area(ba), _area(bb)
    # Prefer the smaller (tighter) box when one largely contains the other.
    if containment_ratio(ba, bb) >= 0.90 and area_b >= area_a * 1.05:
        return a
    if containment_ratio(bb, ba) >= 0.90 and area_a >= area_b * 1.05:
        return b
    if a.detection_confidence != b.detection_confidence:
        return a if a.detection_confidence >= b.detection_confidence else b
    # Deterministic tie-break: lexicographic polygon then model name.
    if a.polygon_norm != b.polygon_norm:
        return a if a.polygon_norm < b.polygon_norm else b
    return a if a.detector_model_name <= b.detector_model_name else b


def _should_keep_both(
    a: DetectedTextRegion,
    b: DetectedTextRegion,
    *,
    neighbour_iou: float,
    equivalent_iou: float,
) -> bool:
    """True when overlap is partial (fragments) rather than equivalent or neighbour."""

    if _are_equivalent(a, b, equivalent_iou=equivalent_iou):
        return False
    iou = bbox_iou(_bbox(a), _bbox(b))
    # Partial overlap: retain both for fragment analysis rather than collapsing
    # to the larger box alone. Unrelated neighbours (low IoU) stay separate.
    return iou >= neighbour_iou


def _combine_provenance(
    primary: DetectedTextRegion,
    others: list[DetectedTextRegion],
) -> DetectedTextRegion:
    names: list[str] = []
    confs: list[float] = []
    for region in [primary, *others]:
        if region.source_detector_names:
            for n, c in zip(region.source_detector_names, region.source_confidences, strict=False):
                if n not in names:
                    names.append(n)
                    confs.append(float(c))
        else:
            if region.detector_model_name not in names:
                names.append(region.detector_model_name)
                confs.append(float(region.detection_confidence))
    names_t = tuple(names)
    confs_t = tuple(confs)
    merged_name = "+".join(sorted(set(names_t)))
    region_id = _stable_merged_id(
        page_index=primary.page_index,
        polygon_norm=primary.polygon_norm,
        source_names=names_t,
    )
    return replace(
        primary,
        region_id=region_id,
        detector_model_name=merged_name,
        detection_confidence=max(confs_t) if confs_t else primary.detection_confidence,
        source_detector_names=names_t,
        source_confidences=confs_t,
        merge_version=DETECTOR_DUAL_MERGE_VERSION,
    )


def merge_detector_regions(
    primary: list[DetectedTextRegion],
    secondary: list[DetectedTextRegion],
    *,
    equivalent_iou: float = DETECTOR_MERGE_EQUIVALENT_IOU,
    neighbour_iou: float = DETECTOR_MERGE_NEIGHBOUR_IOU,
    merge_version: str = DETECTOR_DUAL_MERGE_VERSION,
) -> list[DetectedTextRegion]:
    """Deterministic union of two detector outputs on the same page.

    Fragments with partial overlap are retained (not collapsed to the larger
    box). Exact/equivalent overlaps become one region with combined provenance.
    Distinct neighbouring lines (IoU < neighbour threshold) remain separate.
    """

    if merge_version != DETECTOR_DUAL_MERGE_VERSION:
        raise ValueError(f"unsupported merge version: {merge_version}")

    # Stable input order: primary first, then secondary; sort by geometry.
    pooled = list(primary) + list(secondary)
    pooled.sort(
        key=lambda r: (
            r.page_index,
            r.bbox_norm[1],
            r.bbox_norm[0],
            -r.detection_confidence,
            r.detector_model_name,
            r.polygon_norm,
        )
    )

    clusters: list[list[DetectedTextRegion]] = []
    for region in pooled:
        placed = False
        for cluster in clusters:
            # Compare against every member; equivalent → join; keep-both fragments
            # join the same analysis cluster but geometry preference is later.
            for member in cluster:
                if _are_equivalent(region, member, equivalent_iou=equivalent_iou):
                    cluster.append(region)
                    placed = True
                    break
                if _should_keep_both(
                    region,
                    member,
                    neighbour_iou=neighbour_iou,
                    equivalent_iou=equivalent_iou,
                ):
                    # Partial overlap: attach as fragment sibling in same cluster
                    # for provenance, but emit separately below.
                    cluster.append(region)
                    placed = True
                    break
            if placed:
                break
        if not placed:
            clusters.append([region])

    merged: list[DetectedTextRegion] = []
    for cluster in clusters:
        # Partition cluster into equivalent groups vs fragment siblings.
        groups: list[list[DetectedTextRegion]] = []
        for region in cluster:
            assigned = False
            for group in groups:
                if any(_are_equivalent(region, g, equivalent_iou=equivalent_iou) for g in group):
                    group.append(region)
                    assigned = True
                    break
            if not assigned:
                groups.append([region])

        for group in groups:
            chosen = group[0]
            for other in group[1:]:
                chosen = _prefer_region(chosen, other)
            others = [r for r in group if r is not chosen]
            # Also attach non-equivalent fragment siblings' provenance when they
            # share the cluster but form their own groups — emit each group.
            merged.append(_combine_provenance(chosen, others if others else group[1:]))

    # Re-number order_index deterministically.
    merged.sort(
        key=lambda r: (
            r.page_index,
            r.bbox_norm[1],
            r.bbox_norm[0],
            -r.detection_confidence,
            r.region_id,
        )
    )
    result: list[DetectedTextRegion] = []
    for order_index, region in enumerate(merged):
        result.append(replace(region, order_index=order_index))
    return result

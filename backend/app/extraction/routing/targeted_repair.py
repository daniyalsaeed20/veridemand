"""Targeted region repair facade (Correction 6).

Public helpers remain import-stable. Execution lives in repair_* modules.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from backend.app.contracts.native import NativeWord
from backend.app.contracts.repair import RepairMethod, RepairRegionRecord
from backend.app.contracts.routing import RepairRegionDiagnostics
from backend.app.extraction.routing.models import RoutingPolicy
from backend.app.extraction.routing.repair_clustering import (
    cluster_failed_boxes as _cluster_failed_boxes,
)
from backend.app.extraction.routing.repair_clustering import expand_bbox
from backend.app.extraction.routing.repair_eligibility import evaluate_targeted_repair_eligibility
from PIL import Image

# Back-compat alias used by older tests/imports.
FailedRegion = RepairRegionRecord


def cluster_failed_boxes(
    words: Sequence[NativeWord],
    failed_indices: Sequence[int],
    *,
    page_number: int,
    gap: float | None = None,
    policy: RoutingPolicy | None = None,
) -> list[RepairRegionRecord]:
    """Cluster nearby failed boxes into repair regions."""

    from dataclasses import replace

    if policy is None:
        from backend.app.settings.config import get_settings

        policy = RoutingPolicy.from_settings(get_settings())
    if gap is not None:
        policy = replace(policy, repair_cluster_gap=gap)
    return _cluster_failed_boxes(
        words,
        failed_indices,
        page_number=page_number,
        policy=policy,
    )


def should_escalate_to_full_ocr(
    regions: Sequence[RepairRegionRecord],
    policy: RoutingPolicy,
    *,
    fail_ratio: float,
) -> bool:
    if len(regions) > policy.max_repair_regions:
        return True
    if fail_ratio > policy.max_fail_ratio_for_repair:
        return True
    total_coverage = sum(r.page_coverage_ratio for r in regions)
    return total_coverage > policy.max_repair_coverage


def expand_region(
    region: RepairRegionRecord,
    *,
    padding_ratio: float,
) -> tuple[float, float, float, float]:
    bbox = region.normalised_bbox
    expanded = expand_bbox(
        bbox.x,
        bbox.y,
        bbox.x + bbox.width,
        bbox.y + bbox.height,
        padding_ratio=padding_ratio,
    )
    return (
        expanded.x,
        expanded.y,
        expanded.x + expanded.width,
        expanded.y + expanded.height,
    )


def crop_region(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    import math

    w, h = image.size
    x0, y0, x1, y1 = box
    px0 = int(max(0, math.floor(x0 * w)))
    py0 = int(max(0, math.floor(y0 * h)))
    px1 = int(min(w, math.ceil(x1 * w)))
    py1 = int(min(h, math.ceil(y1 * h)))
    if px1 - px0 < 2 or py1 - py0 < 2:
        return image.crop((0, 0, min(2, w), min(2, h)))
    return image.crop((px0, py0, px1, py1))


def repair_regions(
    image: Image.Image,
    words: Sequence[NativeWord],
    failed_indices: Sequence[int],
    policy: RoutingPolicy,
    *,
    page_number: int,
    recognise_region: Callable[[Image.Image], tuple[int, int]],
) -> tuple[list[RepairRegionDiagnostics], bool]:
    """Legacy diagnostic helper — prefer ``run_targeted_repair_pipeline``.

    ``recognise_region`` returns (recognition_count, replacement_count) and must
    not log text or crops.
    """

    regions = cluster_failed_boxes(words, failed_indices, page_number=page_number, policy=policy)
    fail_ratio = (len(failed_indices) / max(1, len(words))) if words else 1.0
    if should_escalate_to_full_ocr(regions, policy, fail_ratio=fail_ratio):
        return [], True

    diagnostics: list[RepairRegionDiagnostics] = []
    for region in regions:
        box = expand_region(region, padding_ratio=policy.repair_padding_ratio)
        crop = crop_region(image, box)
        try:
            import time

            started = time.perf_counter()
            rec_count, replacements = recognise_region(crop)
            duration_ms = int((time.perf_counter() - started) * 1000)
            method = (
                RepairMethod.RECOGNITION_ONLY.value
                if len(region.source_word_ids) <= 3
                else RepairMethod.LOCAL_DETECTION_AND_RECOGNITION.value
            )
            diagnostics.append(
                RepairRegionDiagnostics(
                    repair_region_id=region.repair_region_id,
                    page_number=page_number,
                    repair_method=method,
                    source_box_count=len(region.source_word_ids),
                    crop_width=crop.size[0],
                    crop_height=crop.size[1],
                    recognition_count=rec_count,
                    duration_ms=duration_ms,
                    replacement_count=replacements,
                    reason_codes=["targeted_region_repaired"],
                )
            )
        finally:
            crop.close()
    return diagnostics, False


__all__ = [
    "FailedRegion",
    "cluster_failed_boxes",
    "crop_region",
    "evaluate_targeted_repair_eligibility",
    "expand_region",
    "repair_regions",
    "should_escalate_to_full_ocr",
]

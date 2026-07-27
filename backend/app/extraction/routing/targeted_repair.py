"""Targeted region repair for limited embedded-OCR failures."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from backend.app.contracts.native import NativeWord
from backend.app.contracts.routing import RepairRegionDiagnostics
from backend.app.extraction.routing.models import RoutingPolicy
from PIL import Image


@dataclass(slots=True)
class FailedRegion:
    """Cluster of nearby failed native boxes."""

    region_id: str
    word_indices: list[int]
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def coverage(self) -> float:
        return max(0.0, (self.x1 - self.x0) * (self.y1 - self.y0))


def cluster_failed_boxes(
    words: Sequence[NativeWord],
    failed_indices: Sequence[int],
    *,
    page_number: int,
    gap: float = 0.04,
) -> list[FailedRegion]:
    """Cluster nearby failed boxes into repair regions."""

    items: list[tuple[int, NativeWord]] = [
        (i, words[i]) for i in failed_indices if 0 <= i < len(words)
    ]
    items.sort(key=lambda pair: (pair[1].geometry.bbox.y, pair[1].geometry.bbox.x))
    clusters: list[FailedRegion] = []
    for idx, word in items:
        bbox = word.geometry.bbox
        wx0, wy0 = bbox.x, bbox.y
        wx1, wy1 = bbox.x + bbox.width, bbox.y + bbox.height
        placed = False
        for cluster in clusters:
            # Expand if overlapping / nearby.
            if (
                wx0 <= cluster.x1 + gap
                and wx1 >= cluster.x0 - gap
                and wy0 <= cluster.y1 + gap
                and wy1 >= cluster.y0 - gap
            ):
                cluster.word_indices.append(idx)
                cluster.x0 = min(cluster.x0, wx0)
                cluster.y0 = min(cluster.y0, wy0)
                cluster.x1 = max(cluster.x1, wx1)
                cluster.y1 = max(cluster.y1, wy1)
                placed = True
                break
        if not placed:
            clusters.append(
                FailedRegion(
                    region_id=f"repair_p{page_number:04d}_{len(clusters) + 1:03d}",
                    word_indices=[idx],
                    x0=wx0,
                    y0=wy0,
                    x1=wx1,
                    y1=wy1,
                )
            )
    return clusters


def should_escalate_to_full_ocr(
    regions: Sequence[FailedRegion],
    policy: RoutingPolicy,
    *,
    fail_ratio: float,
) -> bool:
    if len(regions) > policy.max_repair_regions:
        return True
    if fail_ratio > policy.max_fail_ratio_for_repair:
        return True
    total_coverage = sum(r.coverage for r in regions)
    return total_coverage > policy.max_repair_coverage


def expand_region(
    region: FailedRegion,
    *,
    padding_ratio: float,
) -> tuple[float, float, float, float]:
    width = region.x1 - region.x0
    height = region.y1 - region.y0
    pad_x = width * padding_ratio
    pad_y = height * padding_ratio
    return (
        max(0.0, region.x0 - pad_x),
        max(0.0, region.y0 - pad_y),
        min(1.0, region.x1 + pad_x),
        min(1.0, region.y1 + pad_y),
    )


def crop_region(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
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
    """Attempt targeted repair. Returns (diagnostics, escalate_to_full_ocr).

    ``recognise_region`` returns (recognition_count, replacement_count) and must
    not log text or crops.
    """

    regions = cluster_failed_boxes(words, failed_indices, page_number=page_number)
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
            diagnostics.append(
                RepairRegionDiagnostics(
                    repair_region_id=region.region_id,
                    page_number=page_number,
                    repair_method="recognition_only"
                    if len(region.word_indices) <= 3
                    else "local_detect_recognise",
                    source_box_count=len(region.word_indices),
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

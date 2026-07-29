"""Cheap dense-form / page-profile signals for OCR processing policy.

Classification is a processing-policy signal only — not semantic form understanding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.contracts.ocr import PageProcessingProfile

try:
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]
    Image = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class PageProfileResult:
    page_profile: PageProcessingProfile
    profile_confidence: float
    profile_reason_codes: list[str]
    horizontal_line_density: float
    vertical_line_density: float
    grid_intersection_count: int
    small_component_density: float
    checkbox_like_count: int
    median_box_area_ratio: float
    text_region_density: float
    page_edge_density: float


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return float((ordered[mid - 1] + ordered[mid]) / 2.0)


def _box_areas_from_raw(raw_lines: list[Any], page_area: float) -> list[float]:
    areas: list[float] = []
    for line in raw_lines:
        poly = getattr(line, "polygon_px", None) or []
        if len(poly) < 2:
            continue
        xs = [float(p[0]) for p in poly]
        ys = [float(p[1]) for p in poly]
        area = max(0.0, (max(xs) - min(xs)) * (max(ys) - min(ys)))
        if page_area > 0:
            areas.append(area / page_area)
    return areas


def analyse_page_profile(
    image: Any,
    *,
    raw_lines: list[Any] | None = None,
) -> PageProfileResult:
    """Derive a processing profile from inexpensive visual/structural metrics."""

    reasons: list[str] = []
    width, height = 1, 1
    if image is not None and hasattr(image, "size"):
        width, height = int(image.size[0]), int(image.size[1])
    page_area = float(max(1, width * height))

    h_density = 0.0
    v_density = 0.0
    intersections = 0
    small_cc_density = 0.0
    checkbox_like = 0
    edge_density = 0.0

    if np is not None and image is not None:
        gray = image.convert("L") if hasattr(image, "convert") else image
        arr = np.asarray(gray, dtype=np.uint8)
        # Long ruling lines via row/column dark-run density.
        dark = arr < 96
        row_frac = dark.mean(axis=1)
        col_frac = dark.mean(axis=0)
        long_h = int(np.sum(row_frac > 0.55))
        long_v = int(np.sum(col_frac > 0.55))
        h_density = long_h / max(1, height)
        v_density = long_v / max(1, width)
        # Approximate grid intersections from co-occurring long rows/cols.
        intersections = int(min(long_h, long_v) * 0.35)
        # Edge density near page borders.
        border = max(2, min(width, height) // 40)
        edge_mask = np.zeros_like(dark)
        edge_mask[:border, :] = True
        edge_mask[-border:, :] = True
        edge_mask[:, :border] = True
        edge_mask[:, -border:] = True
        edge_density = float(dark[edge_mask].mean()) if edge_mask.any() else 0.0
        # Checkbox-like: compact dark squares via small blob heuristic on subsampled grid.
        step = max(4, min(width, height) // 80)
        for y in range(0, height - step, step):
            for x in range(0, width - step, step):
                patch = dark[y : y + step, x : x + step]
                fill = float(patch.mean())
                if 0.18 <= fill <= 0.55:
                    # Hollow-ish square: edge denser than centre.
                    cy0, cy1 = step // 3, 2 * step // 3
                    cx0, cx1 = step // 3, 2 * step // 3
                    centre = float(patch[cy0:cy1, cx0:cx1].mean()) if cy1 > cy0 else fill
                    if centre + 0.12 < fill:
                        checkbox_like += 1
        small_cc_density = float(min(1.0, checkbox_like / 80.0))

    areas = _box_areas_from_raw(raw_lines or [], page_area)
    median_box = _median(areas)
    text_density = min(1.0, sum(areas))

    profile = PageProcessingProfile.ORDINARY_DOCUMENT
    confidence = 0.45

    if h_density > 0.04 and v_density > 0.03 and intersections >= 8:
        profile = PageProcessingProfile.DENSE_FORM
        confidence = min(0.95, 0.55 + h_density + v_density)
        reasons.extend(["long_horizontal_rules", "long_vertical_rules", "grid_intersections"])
    elif h_density > 0.06 or (intersections >= 12 and text_density > 0.08):
        profile = PageProcessingProfile.DENSE_FORM
        confidence = min(0.9, 0.5 + h_density * 2)
        reasons.append("dense_ruling_lines")
    elif h_density > 0.03 and v_density > 0.02 and text_density > 0.12:
        profile = PageProcessingProfile.TABLE_LIKE
        confidence = 0.65
        reasons.append("table_like_grid")
    elif (raw_lines is not None and len(raw_lines) <= 4 and text_density < 0.04) or (
        text_density < 0.015 and (raw_lines is None or len(raw_lines) <= 6)
    ):
        profile = PageProcessingProfile.SPARSE_DOCUMENT
        confidence = 0.7
        reasons.append("sparse_text_coverage")
    elif edge_density > 0.35 and text_density < 0.08:
        profile = PageProcessingProfile.PHOTO_WITH_TEXT
        confidence = 0.55
        reasons.append("high_edge_density")

    if checkbox_like >= 6 and profile is PageProcessingProfile.ORDINARY_DOCUMENT:
        profile = PageProcessingProfile.DENSE_FORM
        confidence = max(confidence, 0.6)
        reasons.append("checkbox_like_regions")

    if median_box > 0 and median_box < 0.0008 and text_density > 0.05:
        if profile is PageProcessingProfile.ORDINARY_DOCUMENT:
            profile = PageProcessingProfile.DENSE_FORM
            confidence = max(confidence, 0.58)
        reasons.append("small_median_box_size")

    if not reasons:
        reasons.append("ordinary_structure")

    return PageProfileResult(
        page_profile=profile,
        profile_confidence=float(confidence),
        profile_reason_codes=reasons,
        horizontal_line_density=float(h_density),
        vertical_line_density=float(v_density),
        grid_intersection_count=int(intersections),
        small_component_density=float(small_cc_density),
        checkbox_like_count=int(checkbox_like),
        median_box_area_ratio=float(median_box),
        text_region_density=float(text_density),
        page_edge_density=float(edge_density),
    )

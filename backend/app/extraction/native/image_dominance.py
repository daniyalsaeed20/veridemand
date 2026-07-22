"""Image-dominance metrics from pdfplumber image XObject geometry only."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.extraction.native.models import ImageGeom


@dataclass(frozen=True, slots=True)
class ImageDominanceMetrics:
    image_count: int
    largest_image_area_ratio: float
    total_clipped_image_area_ratio: float
    image_dominant: bool


def analyse_image_dominance(
    images: list[ImageGeom],
    *,
    page_width: float,
    page_height: float,
    page_bbox_x0: float,
    page_bbox_top: float,
    dominant_ratio: float,
) -> ImageDominanceMetrics:
    page_area = max(page_width * page_height, 1.0)
    if not images:
        return ImageDominanceMetrics(0, 0.0, 0.0, False)

    areas: list[float] = []
    # Approximate total with a coarse occupancy grid to avoid double-counting overlap.
    grid = 64
    occupied = [[False] * grid for _ in range(grid)]
    cell_w = page_width / grid
    cell_h = page_height / grid

    for img in images:
        x0 = max(img.x0 - page_bbox_x0, 0.0)
        x1 = min(img.x1 - page_bbox_x0, page_width)
        top = max(img.top - page_bbox_top, 0.0)
        bottom = min(img.bottom - page_bbox_top, page_height)
        if x1 <= x0 or bottom <= top:
            continue
        area = (x1 - x0) * (bottom - top)
        areas.append(area / page_area)
        c0 = max(int(x0 / cell_w), 0)
        c1 = min(int(x1 / cell_w), grid - 1)
        r0 = max(int(top / cell_h), 0)
        r1 = min(int(bottom / cell_h), grid - 1)
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                occupied[r][c] = True

    largest = max(areas) if areas else 0.0
    filled = sum(1 for row in occupied for cell in row if cell)
    total_ratio = min(1.0, filled / (grid * grid))
    return ImageDominanceMetrics(
        image_count=len(images),
        largest_image_area_ratio=min(1.0, largest),
        total_clipped_image_area_ratio=total_ratio,
        image_dominant=largest >= dominant_ratio,
    )

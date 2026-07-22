"""Geometric OCR line grouping into provisional visual text blocks."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.contracts.geometry import NormalisedBoundingBox, NormalisedPoint, NormalisedPolygon
from backend.app.contracts.ocr import PrintedOcrLine
from backend.app.contracts.visual import (
    ReadingOrderStatus,
    VisualBlockType,
    VisualTextBlock,
)


@dataclass(frozen=True, slots=True)
class LayoutThresholds:
    """Geometric grouping thresholds (normalised page ratios)."""

    max_vertical_gap_ratio: float
    min_horizontal_overlap_ratio: float
    column_gap_ratio: float


def _line_bbox(line: PrintedOcrLine) -> NormalisedBoundingBox:
    return line.bbox


def _horizontal_overlap_ratio(a: NormalisedBoundingBox, b: NormalisedBoundingBox) -> float:
    left = max(a.x, b.x)
    right = min(a.x + a.width, b.x + b.width)
    overlap = max(0.0, right - left)
    denom = min(a.width, b.width)
    if denom <= 0:
        return 0.0
    return overlap / denom


def _vertical_gap(a: NormalisedBoundingBox, b: NormalisedBoundingBox) -> float:
    if a.y <= b.y:
        return max(0.0, b.y - (a.y + a.height))
    return max(0.0, a.y - (b.y + b.height))


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _union_bbox(boxes: list[NormalisedBoundingBox]) -> NormalisedBoundingBox:
    left = min(b.x for b in boxes)
    top = min(b.y for b in boxes)
    right = max(b.x + b.width for b in boxes)
    bottom = max(b.y + b.height for b in boxes)
    width = max(right - left, 1e-9)
    height = max(bottom - top, 1e-9)
    if left + width > 1.0:
        width = 1.0 - left
    if top + height > 1.0:
        height = 1.0 - top
    return NormalisedBoundingBox(x=left, y=top, width=max(width, 1e-9), height=max(height, 1e-9))


def _bbox_polygon(bbox: NormalisedBoundingBox) -> NormalisedPolygon:
    right = min(bbox.x + bbox.width, 1.0)
    bottom = min(bbox.y + bbox.height, 1.0)
    return NormalisedPolygon(
        points=[
            NormalisedPoint(x=bbox.x, y=bbox.y),
            NormalisedPoint(x=right, y=bbox.y),
            NormalisedPoint(x=right, y=bottom),
            NormalisedPoint(x=bbox.x, y=bottom),
        ]
    )


def group_lines_into_blocks(
    lines: list[PrintedOcrLine],
    *,
    page_number: int,
    thresholds: LayoutThresholds,
) -> list[VisualTextBlock]:
    """Group OCR lines into geometric ``text_unknown`` blocks."""

    if not lines:
        return []

    ordered = sorted(lines, key=lambda line: (_line_bbox(line).y, _line_bbox(line).x))
    heights = [_line_bbox(line).height for line in ordered]
    median_height = max(_median(heights), 1e-4)
    max_gap = max(thresholds.max_vertical_gap_ratio, median_height * 1.5)

    # First pass: cluster by vertical proximity + horizontal overlap.
    clusters: list[list[PrintedOcrLine]] = []
    current: list[PrintedOcrLine] = []
    for line in ordered:
        if not current:
            current = [line]
            continue
        prev = current[-1]
        gap = _vertical_gap(_line_bbox(prev), _line_bbox(line))
        overlap = _horizontal_overlap_ratio(_line_bbox(prev), _line_bbox(line))
        if gap <= max_gap and overlap >= thresholds.min_horizontal_overlap_ratio:
            current.append(line)
        else:
            clusters.append(current)
            current = [line]
    if current:
        clusters.append(current)

    # Column detection: split clusters whose members span a persistent horizontal gap.
    refined: list[list[PrintedOcrLine]] = []
    for cluster in clusters:
        refined.extend(_split_columns(cluster, thresholds.column_gap_ratio))

    blocks: list[VisualTextBlock] = []
    for index, cluster in enumerate(refined):
        boxes = [_line_bbox(line) for line in cluster]
        bbox = _union_bbox(boxes)
        block_id = f"ocrblock_p{page_number:04d}_{index + 1:06d}"
        blocks.append(
            VisualTextBlock(
                id=block_id,
                page_number=page_number,
                sequence_index=index,
                line_ids=[line.id for line in cluster],
                polygon=_bbox_polygon(bbox),
                bbox=bbox,
                block_type=VisualBlockType.TEXT_UNKNOWN,
                reading_order_index=index,
                reading_order_status=ReadingOrderStatus.PROVISIONAL_PHASE_4,
            )
        )
    return blocks


def _split_columns(
    cluster: list[PrintedOcrLine], column_gap_ratio: float
) -> list[list[PrintedOcrLine]]:
    if len(cluster) < 2:
        return [cluster]

    # Sort by x centre; look for a gap larger than threshold between neighbouring centres.
    annotated = sorted(
        cluster,
        key=lambda line: _line_bbox(line).x + _line_bbox(line).width / 2.0,
    )
    centres = [_line_bbox(line).x + _line_bbox(line).width / 2.0 for line in annotated]
    split_at: list[int] = []
    for i in range(len(centres) - 1):
        left_box = _line_bbox(annotated[i])
        right_box = _line_bbox(annotated[i + 1])
        gap = right_box.x - (left_box.x + left_box.width)
        if gap >= column_gap_ratio:
            split_at.append(i + 1)

    if not split_at:
        return [cluster]

    parts: list[list[PrintedOcrLine]] = []
    start = 0
    for cut in split_at:
        parts.append(annotated[start:cut])
        start = cut
    parts.append(annotated[start:])
    # Re-sort each column top-to-bottom.
    result: list[list[PrintedOcrLine]] = []
    for part in parts:
        if not part:
            continue
        result.append(sorted(part, key=lambda line: (_line_bbox(line).y, _line_bbox(line).x)))
    return result

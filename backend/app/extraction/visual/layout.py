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
    """Group OCR lines into geometric ``text_unknown`` blocks.

    Deterministic provisional grouping only — no semantic structure.
    Prevents distant columns joining and dissimilar-height form rows merging.
    """

    if not lines:
        return []

    ordered = sorted(lines, key=lambda line: (_line_bbox(line).y, _line_bbox(line).x))
    heights = [_line_bbox(line).height for line in ordered]
    median_height = max(_median(heights), 1e-4)
    max_gap = max(thresholds.max_vertical_gap_ratio, median_height * 1.5)

    # First pass: cluster by vertical proximity + horizontal overlap + height similarity.
    clusters: list[list[PrintedOcrLine]] = []
    current: list[PrintedOcrLine] = []
    for line in ordered:
        if not current:
            current = [line]
            continue
        prev = current[-1]
        gap = _vertical_gap(_line_bbox(prev), _line_bbox(line))
        overlap = _horizontal_overlap_ratio(_line_bbox(prev), _line_bbox(line))
        h_prev = max(_line_bbox(prev).height, 1e-6)
        h_cur = max(_line_bbox(line).height, 1e-6)
        height_ratio = max(h_prev, h_cur) / min(h_prev, h_cur)
        # Dissimilar heights (e.g. form label vs body) should not merge into one row cluster.
        if (
            gap <= max_gap
            and overlap >= thresholds.min_horizontal_overlap_ratio
            and height_ratio <= 2.2
        ):
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


@dataclass(frozen=True, slots=True)
class GroupingQualityMetrics:
    """Privacy-safe provisional line-grouping quality metrics."""

    words_grouped: int
    single_word_line_count: int
    single_character_line_count: int
    unassigned_item_count: int
    line_overlap_count: int


def compute_grouping_quality(
    lines: list[PrintedOcrLine],
    blocks: list[VisualTextBlock],
    *,
    total_items_before_filter: int | None = None,
) -> GroupingQualityMetrics:
    assigned = {lid for block in blocks for lid in block.line_ids}
    single_word = 0
    single_char = 0
    for line in lines:
        tokens = line.normalised_text.split()
        if len(tokens) <= 1:
            single_word += 1
        if len(line.normalised_text.strip()) == 1:
            single_char += 1
    overlap = 0
    for i, a in enumerate(lines):
        for b in lines[i + 1 :]:
            if _horizontal_overlap_ratio(a.bbox, b.bbox) > 0.8:
                va = max(
                    0.0,
                    min(a.bbox.y + a.bbox.height, b.bbox.y + b.bbox.height)
                    - max(a.bbox.y, b.bbox.y),
                )
                if va > 0.5 * min(a.bbox.height, b.bbox.height):
                    overlap += 1
    unassigned = max(0, (total_items_before_filter or len(lines)) - len(assigned))
    return GroupingQualityMetrics(
        words_grouped=len(assigned),
        single_word_line_count=single_word,
        single_character_line_count=single_char,
        unassigned_item_count=unassigned,
        line_overlap_count=overlap,
    )


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

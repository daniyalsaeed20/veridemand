"""Unit tests for provisional visual layout grouping."""

from __future__ import annotations

from backend.app.contracts.geometry import NormalisedBoundingBox, NormalisedPoint, NormalisedPolygon
from backend.app.contracts.ocr import (
    OcrRecognitionStatus,
    PixelBoundingBox,
    PixelPolygon,
    PreprocessingVariant,
    PrintedOcrLine,
)
from backend.app.extraction.visual.layout import LayoutThresholds, group_lines_into_blocks
from backend.app.extraction.visual.reading_order import build_reading_order


def _line(
    page: int, index: int, x: float, y: float, w: float, h: float, text: str
) -> PrintedOcrLine:
    bbox = NormalisedBoundingBox(x=x, y=y, width=w, height=h)
    polygon = NormalisedPolygon(
        points=[
            NormalisedPoint(x=x, y=y),
            NormalisedPoint(x=x + w, y=y),
            NormalisedPoint(x=x + w, y=y + h),
            NormalisedPoint(x=x, y=y + h),
        ]
    )
    return PrintedOcrLine(
        id=f"ocrline_p{page:04d}_{index:06d}",
        page_number=page,
        sequence_index=index,
        text=text,
        normalised_text=text,
        detection_score=0.9,
        recognition_score=0.9,
        recognition_status=OcrRecognitionStatus.ACCEPTED,
        polygon=polygon,
        bbox=bbox,
        pixel_polygon=PixelPolygon(points=[(0, 0), (1, 0), (1, 1), (0, 1)]),
        pixel_bbox=PixelBoundingBox(x=0, y=0, width=1, height=1),
        preprocessing_variant=PreprocessingVariant.ORIGINAL_RGB,
    )


def test_single_column_grouping() -> None:
    lines = [
        _line(1, 0, 0.1, 0.1, 0.5, 0.03, "one"),
        _line(1, 1, 0.1, 0.14, 0.5, 0.03, "two"),
        _line(1, 2, 0.1, 0.18, 0.5, 0.03, "three"),
    ]
    thresholds = LayoutThresholds(
        max_vertical_gap_ratio=0.035,
        min_horizontal_overlap_ratio=0.25,
        column_gap_ratio=0.08,
    )
    blocks = group_lines_into_blocks(lines, page_number=1, thresholds=thresholds)
    assert len(blocks) == 1
    assert blocks[0].line_ids == [line.id for line in lines]
    order = build_reading_order(lines, blocks)
    assert order.line_ids == [line.id for line in lines]


def test_two_columns_ordered_left_to_right() -> None:
    lines = [
        _line(1, 0, 0.05, 0.1, 0.3, 0.03, "L1"),
        _line(1, 1, 0.05, 0.15, 0.3, 0.03, "L2"),
        _line(1, 2, 0.55, 0.1, 0.3, 0.03, "R1"),
        _line(1, 3, 0.55, 0.15, 0.3, 0.03, "R2"),
    ]
    thresholds = LayoutThresholds(
        max_vertical_gap_ratio=0.035,
        min_horizontal_overlap_ratio=0.25,
        column_gap_ratio=0.08,
    )
    blocks = group_lines_into_blocks(lines, page_number=1, thresholds=thresholds)
    assert len(blocks) >= 2
    order = build_reading_order(lines, blocks)
    # Left column lines should appear before right column.
    assert order.line_ids.index(lines[0].id) < order.line_ids.index(lines[2].id)

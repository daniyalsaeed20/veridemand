"""Provisional geometric reading order for Phase 4 display."""

from __future__ import annotations

from backend.app.contracts.ocr import PrintedOcrLine
from backend.app.contracts.visual import (
    ReadingOrderMethod,
    ReadingOrderStatus,
    VisualReadingOrder,
    VisualTextBlock,
)


def build_reading_order(
    lines: list[PrintedOcrLine],
    blocks: list[VisualTextBlock],
) -> VisualReadingOrder:
    """Order columns left-to-right, lines top-to-bottom within each block.

    The original OCR detection sequence is retained as diagnostic metadata only.
    """

    diagnostic = [line.id for line in lines]

    # Blocks are already ordered by layout grouping (columns L→R, lines T→B).
    ordered_blocks = sorted(blocks, key=lambda b: (b.bbox.x, b.bbox.y, b.sequence_index))
    line_ids: list[str] = []
    block_ids: list[str] = []
    seen_lines: set[str] = set()
    for block in ordered_blocks:
        block_ids.append(block.id)
        for line_id in block.line_ids:
            if line_id not in seen_lines:
                line_ids.append(line_id)
                seen_lines.add(line_id)

    # Append any lines not assigned to a block (should be rare).
    for line in sorted(lines, key=lambda item: (item.bbox.y, item.bbox.x, item.sequence_index)):
        if line.id not in seen_lines:
            line_ids.append(line.id)

    return VisualReadingOrder(
        order_method=ReadingOrderMethod.GEOMETRIC_COLUMNS_PHASE_4,
        order_status=ReadingOrderStatus.PROVISIONAL_PHASE_4,
        line_ids=line_ids,
        block_ids=block_ids,
        diagnostic_ocr_sequence_line_ids=diagnostic,
    )


def apply_block_reading_order_indices(blocks: list[VisualTextBlock]) -> list[VisualTextBlock]:
    """Rewrite ``reading_order_index`` to match left-to-right / top-to-bottom order."""

    ordered = sorted(blocks, key=lambda b: (b.bbox.x, b.bbox.y, b.sequence_index))
    updated: list[VisualTextBlock] = []
    for index, block in enumerate(ordered):
        updated.append(block.model_copy(update={"reading_order_index": index}))
    return updated

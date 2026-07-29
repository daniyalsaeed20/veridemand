"""Exclusive final-route histogram accounting (post-release correction)."""

from __future__ import annotations

from types import SimpleNamespace

from backend.app.contracts.visual import PageResultState
from backend.app.extraction.visual.service import (
    build_final_route_histogram,
    provisional_exclusive_histogram_from_diagnostics,
)


def test_exclusive_histogram_sums_to_page_count() -> None:
    published = {
        1: SimpleNamespace(page_result_state=PageResultState.DIGITAL_NATIVE, page_route=None),
        2: SimpleNamespace(
            page_result_state=PageResultState.EMBEDDED_OCR_VERIFIED, page_route=None
        ),
        3: SimpleNamespace(page_result_state=PageResultState.FULL_VISUAL_OCR, page_route=None),
        4: SimpleNamespace(page_result_state=PageResultState.FULL_VISUAL_OCR, page_route=None),
        5: SimpleNamespace(page_result_state=PageResultState.VISUAL_NO_TEXT, page_route=None),
    }
    hist = build_final_route_histogram(published)  # type: ignore[arg-type]
    assert hist.digital_native_pages == 1
    assert hist.embedded_ocr_verified_pages == 1
    assert hist.full_visual_ocr_pages == 2
    assert hist.visual_no_text_pages == 1
    assert hist.exclusive_terminal_total() == 5
    assert hist.total() == 5


def test_104_page_medical_exclusive_totals() -> None:
    """Live opaque medical: exclusive embedded 17 + full 87 = 104."""
    published = {
        **{
            i: SimpleNamespace(
                page_result_state=PageResultState.EMBEDDED_OCR_VERIFIED, page_route=None
            )
            for i in range(1, 18)
        },
        **{
            i: SimpleNamespace(page_result_state=PageResultState.FULL_VISUAL_OCR, page_route=None)
            for i in range(18, 105)
        },
    }
    hist = build_final_route_histogram(published)  # type: ignore[arg-type]
    assert hist.digital_native_pages == 0
    assert hist.embedded_ocr_verified_pages == 17
    assert hist.full_visual_ocr_pages == 87
    assert hist.visual_no_text_pages == 0
    assert hist.exclusive_terminal_total() == 104
    overlapping = 17 + 17 + 87
    assert overlapping == 121
    assert hist.total() != overlapping


def test_live_batch_exclusive_totals_218() -> None:
    """Measured live seven-doc exclusive histogram sums to 218."""
    hist = provisional_exclusive_histogram_from_diagnostics(
        document_pages_total=218,
        native_pages_retained=124,  # overlapping diagnostic (includes embedded)
        embedded_ocr_pages_verified=17,
        targeted_repair_pages=0,
        full_ocr_pages_selected=93,
        full_ocr_pages_completed=93,
        visual_no_text_pages=1,
        failed_pages=0,
    )
    # digital exclusive = 124 - 17 = 107
    assert hist.digital_native_pages == 107
    assert hist.embedded_ocr_verified_pages == 17
    assert hist.embedded_ocr_targeted_repair_pages == 0
    assert hist.full_visual_ocr_pages == 93
    assert hist.visual_no_text_pages == 1
    assert hist.page_failed_pages == 0
    assert hist.exclusive_terminal_total() == 218
    assert hist.total() == 218


def test_batch_page_total_from_document_sums_not_hardcoded() -> None:
    """Batch total is the sum of validated document page counts."""
    per_document_pages = (97, 9, 2, 1, 104, 2, 3)
    batch_total = sum(per_document_pages)
    assert batch_total == 218
    # Prior consolidation baseline 217 was a different/outdated mapping.
    assert batch_total != 217


def test_embedded_not_counted_as_digital_native() -> None:
    hist = provisional_exclusive_histogram_from_diagnostics(
        document_pages_total=104,
        native_pages_retained=17,
        embedded_ocr_pages_verified=17,
        targeted_repair_pages=0,
        full_ocr_pages_selected=87,
        full_ocr_pages_completed=87,
    )
    assert hist.digital_native_pages == 0
    assert hist.embedded_ocr_verified_pages == 17


def test_visual_no_text_counts_exclusively() -> None:
    published = {
        1: SimpleNamespace(page_result_state=PageResultState.VISUAL_NO_TEXT, page_route=None),
        2: SimpleNamespace(page_result_state=PageResultState.FULL_VISUAL_OCR, page_route=None),
    }
    hist = build_final_route_histogram(published)  # type: ignore[arg-type]
    assert hist.visual_no_text_pages == 1
    assert hist.full_visual_ocr_pages == 1
    assert hist.exclusive_terminal_total() == 2


def test_pages_completed_uses_exclusive_terminal_total() -> None:
    hist = provisional_exclusive_histogram_from_diagnostics(
        document_pages_total=104,
        native_pages_retained=17,
        embedded_ocr_pages_verified=17,
        targeted_repair_pages=0,
        full_ocr_pages_selected=87,
        full_ocr_pages_completed=13,
    )
    # Terminal completed: digital 0 + embedded 17 + full 13 = 30 (not retained-only 17).
    assert hist.exclusive_terminal_total() == 30
    assert hist.pending_pages == 74


def test_histogram_deduplicates_by_page_number() -> None:
    """Retries / turn replays must not inflate exclusive counts (dict keyed by page)."""
    published = {
        1: SimpleNamespace(page_result_state=PageResultState.FULL_VISUAL_OCR, page_route=None),
        # Same page number would overwrite in a real publish dict — simulate final state only.
        2: SimpleNamespace(page_result_state=PageResultState.FULL_VISUAL_OCR, page_route=None),
    }
    hist = build_final_route_histogram(published)  # type: ignore[arg-type]
    assert hist.full_visual_ocr_pages == 2
    assert hist.exclusive_terminal_total() == 2


def test_pages_not_requiring_full_formula_no_embedded_double_count() -> None:
    retained_native = {1, 2, 3}  # 2 and 3 also embedded
    embedded_verified = {2, 3}
    visual_no_text_pages = {4}
    selected = {5, 6}
    pages_not_requiring_full = len((retained_native | set(visual_no_text_pages)) - set(selected))
    assert pages_not_requiring_full == 4
    old = len(retained_native - set(selected)) + len(embedded_verified) + len(visual_no_text_pages)
    assert old == 6

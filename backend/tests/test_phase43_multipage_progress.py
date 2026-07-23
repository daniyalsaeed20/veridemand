"""Phase 4.3 multipage visual progress and operation lifecycle."""

from __future__ import annotations

from backend.app.processing.progress_model import (
    OVERALL_CAP,
    OVERALL_PAGE_PROCESSING_END,
    OVERALL_PAGE_PROCESSING_START,
    OVERALL_SUMMARY_START,
    OVERALL_VISUAL_SELECT_END,
    PAGE_PUBLISHED,
    PAGE_QUEUED,
    MajorPhase,
    OperationStatus,
    ProgressSnapshot,
)


def test_two_page_progress_does_not_reach_65_after_page_1() -> None:
    snap = ProgressSnapshot(overall_percent=35.0)
    snap.major_phase = MajorPhase.VISUAL_OCR
    snap.set_visual_selection_complete(pages_selected=2)
    snap.set_visual_visibility_complete()
    snap.set_visual_page_progress(
        pages_completed=0, pages_selected=2, page_number=1, page_percent=PAGE_QUEUED
    )
    assert snap.overall_percent < 52
    # Page 1 at 100% before counting as completed.
    snap.set_visual_page_progress(
        pages_completed=0, pages_selected=2, page_number=1, page_percent=PAGE_PUBLISHED
    )
    assert 50.0 <= snap.overall_percent <= 53.0
    assert snap.overall_percent < OVERALL_CAP
    # After publish: completed=1, do not include page percent again.
    snap.set_visual_page_progress(
        pages_completed=1,
        pages_selected=2,
        page_number=1,
        page_percent=PAGE_PUBLISHED,
        include_page_in_fraction=False,
    )
    mid = snap.overall_percent
    assert 50.0 <= mid <= 53.0
    assert mid < OVERALL_CAP


def test_page_1_completion_is_midpoint_visual_progress() -> None:
    snap = ProgressSnapshot(overall_percent=41.0)
    snap.major_phase = MajorPhase.VISUAL_OCR
    snap.set_visual_page_progress(
        pages_completed=0, pages_selected=2, page_number=1, page_percent=100.0
    )
    assert abs(snap.overall_percent - 52.0) < 0.6


def test_page_2_start_does_not_regress_overall_or_phase() -> None:
    snap = ProgressSnapshot(overall_percent=41.0)
    snap.major_phase = MajorPhase.VISUAL_OCR
    snap.set_visual_page_progress(
        pages_completed=1,
        pages_selected=2,
        page_number=1,
        page_percent=100.0,
        include_page_in_fraction=False,
    )
    overall_after_p1 = snap.overall_percent
    phase_after_p1 = snap.major_phase_percent
    snap.set_visual_page_progress(
        pages_completed=1, pages_selected=2, page_number=2, page_percent=PAGE_QUEUED
    )
    assert snap.overall_percent >= overall_after_p1
    assert snap.major_phase_percent >= phase_after_p1
    assert snap.page_percent == PAGE_QUEUED
    assert snap.page_number == 2


def test_overall_and_major_phase_are_monotonic() -> None:
    snap = ProgressSnapshot(overall_percent=35.0)
    snap.major_phase = MajorPhase.VISUAL_OCR
    values: list[float] = []
    phases: list[float] = []
    snap.set_visual_selection_complete(pages_selected=2)
    values.append(snap.overall_percent)
    phases.append(snap.major_phase_percent)
    snap.set_visual_visibility_complete()
    values.append(snap.overall_percent)
    phases.append(snap.major_phase_percent)
    for pct in (5.0, 25.0, 70.0, 100.0):
        snap.set_visual_page_progress(
            pages_completed=0, pages_selected=2, page_number=1, page_percent=pct
        )
        values.append(snap.overall_percent)
        phases.append(snap.major_phase_percent)
    snap.set_visual_page_progress(
        pages_completed=1,
        pages_selected=2,
        page_number=1,
        page_percent=100.0,
        include_page_in_fraction=False,
    )
    values.append(snap.overall_percent)
    phases.append(snap.major_phase_percent)
    for pct in (5.0, 100.0):
        snap.set_visual_page_progress(
            pages_completed=1, pages_selected=2, page_number=2, page_percent=pct
        )
        values.append(snap.overall_percent)
        phases.append(snap.major_phase_percent)
    snap.set_visual_summary_progress()
    values.append(snap.overall_percent)
    phases.append(snap.major_phase_percent)
    snap.set_visual_complete()
    values.append(snap.overall_percent)
    phases.append(snap.major_phase_percent)
    assert values == sorted(values)
    assert phases == sorted(phases)
    assert values[-1] == OVERALL_CAP


def test_page_progress_may_reset_when_page_number_changes() -> None:
    snap = ProgressSnapshot()
    snap.major_phase = MajorPhase.VISUAL_OCR
    snap.set_visual_page_progress(
        pages_completed=0, pages_selected=2, page_number=1, page_percent=100.0
    )
    assert snap.page_percent == 100.0
    snap.set_visual_page_progress(
        pages_completed=1, pages_selected=2, page_number=2, page_percent=5.0
    )
    assert snap.page_number == 2
    assert snap.page_percent == 5.0


def test_operation_start_has_one_terminal() -> None:
    snap = ProgressSnapshot()
    snap.begin_operation("paddle_ocr_pipeline")
    assert snap.operation_is_open
    assert snap.operation_status is OperationStatus.STARTED
    snap.terminal_operation(OperationStatus.COMPLETED)
    assert not snap.operation_is_open
    assert snap.operation_status is OperationStatus.COMPLETED
    assert len(snap.history) == 1
    assert snap.history[0]["operation"] == "paddle_ocr_pipeline"
    assert snap.history[0]["status"] == "completed"


def test_complete_open_operation_is_idempotent() -> None:
    snap = ProgressSnapshot()
    snap.begin_operation("visual_page_render")
    assert snap.complete_open_operation() is True
    assert snap.complete_open_operation() is False


def test_selection_band_and_page_band_constants() -> None:
    snap = ProgressSnapshot(overall_percent=35.0)
    snap.major_phase = snap.major_phase.VISUAL_OCR
    snap.set_visual_selection_complete(pages_selected=2)
    assert snap.overall_percent == OVERALL_VISUAL_SELECT_END
    snap.set_visual_visibility_complete()
    assert snap.overall_percent == OVERALL_PAGE_PROCESSING_START
    snap.set_visual_page_progress(
        pages_completed=2,
        pages_selected=2,
        page_number=2,
        page_percent=100.0,
        include_page_in_fraction=False,
    )
    assert snap.overall_percent == OVERALL_PAGE_PROCESSING_END
    snap.set_visual_summary_progress()
    assert snap.overall_percent == OVERALL_SUMMARY_START


def test_deadline_remaining_refreshed_independently_of_history() -> None:
    snap = ProgressSnapshot()
    snap.deadline_remaining_seconds = 100.0
    snap.begin_operation("paddle_ocr_pipeline")
    snap.deadline_remaining_seconds = 42.5
    snap.terminal_operation(OperationStatus.COMPLETED)
    assert snap.deadline_remaining_seconds == 42.5
    assert snap.history[-1]["deadline_remaining_seconds"] == 42.5


def test_elapsed_fields_are_distinct() -> None:
    snap = ProgressSnapshot()
    snap.begin_page(1)
    snap.begin_operation("visual_page_render")
    snap.mark_real_progress()
    assert snap.document_elapsed_seconds >= 0
    assert snap.page_elapsed_seconds is not None
    assert snap.operation_elapsed_seconds >= 0
    assert snap.elapsed_seconds == snap.document_elapsed_seconds

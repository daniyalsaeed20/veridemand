"""Simulate two-page visual progress event sequence through ProgressSnapshot lifecycle."""

from __future__ import annotations

from backend.app.processing.progress_model import (
    OVERALL_CAP,
    PAGE_GROUPED,
    PAGE_MAPPING_DONE,
    PAGE_OCR_PIPELINE_DONE,
    PAGE_PREPROCESSED,
    PAGE_PUBLISHED,
    PAGE_QUEUED,
    PAGE_RENDERED,
    MajorPhase,
    OperationStatus,
    ProgressKind,
    ProgressSnapshot,
)


def _run_page(snap: ProgressSnapshot, *, page: int, completed_before: int, selected: int) -> int:
    snap.complete_open_operation()
    snap.begin_page(page)
    snap.begin_operation("visual_page_render")
    snap.set_visual_page_progress(
        pages_completed=completed_before,
        pages_selected=selected,
        page_number=page,
        page_percent=PAGE_QUEUED,
    )
    snap.terminal_operation(OperationStatus.COMPLETED)

    snap.begin_operation("visual_preprocessing")
    snap.set_visual_page_progress(
        pages_completed=completed_before,
        pages_selected=selected,
        page_number=page,
        page_percent=PAGE_RENDERED,
    )
    snap.terminal_operation(OperationStatus.COMPLETED)

    snap.begin_operation("paddle_ocr_pipeline", status=OperationStatus.STARTED)
    snap.progress_kind = ProgressKind.INDETERMINATE
    snap.set_visual_page_progress(
        pages_completed=completed_before,
        pages_selected=selected,
        page_number=page,
        page_percent=PAGE_PREPROCESSED,
    )
    # Heartbeat must not advance percent.
    before = snap.overall_percent
    snap.mark_heartbeat()
    assert snap.overall_percent == before
    snap.progress_kind = ProgressKind.DETERMINATE
    snap.set_visual_page_progress(
        pages_completed=completed_before,
        pages_selected=selected,
        page_number=page,
        page_percent=PAGE_OCR_PIPELINE_DONE,
    )
    snap.terminal_operation(OperationStatus.COMPLETED)
    assert snap.history[-1]["operation"] == "paddle_ocr_pipeline"
    assert snap.history[-1]["status"] == "completed"

    snap.begin_operation("visual_coordinate_mapping")
    snap.set_visual_page_progress(
        pages_completed=completed_before,
        pages_selected=selected,
        page_number=page,
        page_percent=PAGE_MAPPING_DONE,
    )
    snap.terminal_operation(OperationStatus.COMPLETED)

    snap.begin_operation("visual_line_grouping")
    snap.set_visual_page_progress(
        pages_completed=completed_before,
        pages_selected=selected,
        page_number=page,
        page_percent=PAGE_GROUPED,
    )
    snap.terminal_operation(OperationStatus.COMPLETED)

    snap.begin_operation("visual_page_publication")
    snap.set_visual_page_progress(
        pages_completed=completed_before,
        pages_selected=selected,
        page_number=page,
        page_percent=PAGE_PUBLISHED,
    )
    snap.terminal_operation(OperationStatus.COMPLETED)
    completed = completed_before + 1
    snap.set_visual_page_progress(
        pages_completed=completed,
        pages_selected=selected,
        page_number=page,
        page_percent=PAGE_PUBLISHED,
        include_page_in_fraction=False,
    )
    return completed


def test_two_page_lifecycle_reaches_65_only_after_summary() -> None:
    snap = ProgressSnapshot(overall_percent=35.0, major_phase=MajorPhase.VISUAL_OCR)
    overalls: list[float] = []

    snap.begin_operation("visual_page_selection")
    snap.set_visual_selection_complete(pages_selected=2)
    snap.terminal_operation(OperationStatus.COMPLETED)
    overalls.append(snap.overall_percent)
    selection_starts = sum(1 for h in snap.history if h["operation"] == "visual_page_selection")
    assert selection_starts == 1

    snap.set_visual_visibility_complete()
    overalls.append(snap.overall_percent)

    completed = _run_page(snap, page=1, completed_before=0, selected=2)
    overalls.append(snap.overall_percent)
    assert snap.overall_percent < OVERALL_CAP
    assert completed == 1

    completed = _run_page(snap, page=2, completed_before=completed, selected=2)
    overalls.append(snap.overall_percent)
    assert snap.overall_percent <= 63.0
    assert completed == 2

    snap.begin_operation("visual_summary_publication")
    snap.set_visual_summary_progress()
    snap.terminal_operation(OperationStatus.COMPLETED)
    overalls.append(snap.overall_percent)

    snap.begin_operation("visual_authority_reconciliation")
    snap.set_visual_authority_progress()
    snap.terminal_operation(OperationStatus.COMPLETED)
    overalls.append(snap.overall_percent)

    snap.set_visual_complete()
    overalls.append(snap.overall_percent)
    assert snap.overall_percent == OVERALL_CAP
    assert overalls == sorted(overalls)

    ops = [h["operation"] for h in snap.history]
    assert ops.count("visual_page_selection") == 1
    assert "paddle_ocr_pipeline" in ops
    assert "visual_summary_publication" in ops
    assert "visual_authority_reconciliation" in ops
    assert "paddle_text_detection" not in ops
    # Every history entry is a terminal status.
    assert all(
        h["status"] in {"completed", "failed", "timed_out", "cancelled", "skipped"}
        for h in snap.history
    )


def test_progress_events_never_include_ocr_text_keys() -> None:
    snap = ProgressSnapshot(overall_percent=41.0, major_phase=MajorPhase.VISUAL_OCR)
    snap.begin_operation("paddle_ocr_pipeline")
    snap.terminal_operation(OperationStatus.COMPLETED)
    blob = str(snap.history)
    for forbidden in ("rec_text", "ocr_text", "recognized_text", "line_text"):
        assert forbidden not in blob

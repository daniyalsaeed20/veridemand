"""Correction 4 — progress lifecycle, page semantics, clocks, and ETA."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.contracts.progress import ProgressEvent, ProgressEventType
from backend.app.processing.operation_lifecycle import (
    OperationAttemptId,
    OperationLifecycleLedger,
)
from backend.app.processing.progress_model import (
    OVERALL_CAP,
    PAGE_OCR_PIPELINE_DONE,
    PAGE_PUBLISHED,
    OperationStatus,
    ProgressSnapshot,
    SlowWarningStatus,
)


def test_document_and_selected_page_fields_stay_distinct() -> None:
    snap = ProgressSnapshot(document_id="doc_1", document_pages_total=104)
    snap.begin_page(
        20,
        selected_page_index=1,
        selected_pages_total=2,
        visual_page_index=1,
        visual_pages_total=2,
    )
    snap.set_visual_page_progress(
        pages_completed=0,
        pages_selected=2,
        page_number=20,
        page_percent=PAGE_OCR_PIPELINE_DONE,
        selected_page_index=1,
        document_pages_total=104,
    )
    assert snap.document_page_number == 20
    assert snap.document_pages_total == 104
    assert snap.selected_page_index == 1
    assert snap.selected_pages_total == 2
    assert snap.page_number == 20
    assert snap.pages_total == 2


def test_progress_event_rejects_index_exceeding_total() -> None:
    with pytest.raises(ValidationError):
        ProgressEvent(
            event_id="evt_1",
            event_sequence=1,
            event=ProgressEventType.DOCUMENT_VISUAL_PAGE_STARTED,
            session_id="ses_1",
            timestamp=__import__("datetime").datetime.now(__import__("datetime").UTC),
            document_page_number=5,
            document_pages_total=2,
        )


def test_lifecycle_one_started_one_terminal() -> None:
    snap = ProgressSnapshot(document_id="doc_1")
    assert snap.begin_operation("full_ocr_primary")
    assert snap.terminal_operation(OperationStatus.COMPLETED)
    assert not snap.terminal_operation(OperationStatus.COMPLETED)
    assert snap.last_lifecycle_reject is not None
    # Same attempt identity cannot accept another terminal.
    attempt = OperationAttemptId(
        operation_id=snap.operation_id or "missing",
        document_id="doc_1",
        operation="full_ocr_primary",
        attempt_number=1,
        document_page_number=None,
    )
    ledger = snap.ledger
    assert not ledger.register_started(attempt).accepted


def test_retry_creates_new_attempt_identity() -> None:
    snap = ProgressSnapshot(document_id="doc_1")
    assert snap.begin_operation("full_ocr_primary", attempt_number=1)
    op1 = snap.operation_id
    assert snap.terminal_operation(OperationStatus.TIMED_OUT)
    assert snap.begin_operation("full_ocr_primary", attempt_number=2)
    assert snap.operation_id != op1
    assert snap.attempt_number == 2


def test_old_attempt_rejected_by_ledger() -> None:
    ledger = OperationLifecycleLedger()
    a1 = OperationAttemptId(
        operation_id="op1",
        document_id="doc",
        operation="full_ocr_primary",
        attempt_number=1,
        document_page_number=1,
    )
    a2 = OperationAttemptId(
        operation_id="op2",
        document_id="doc",
        operation="full_ocr_primary",
        attempt_number=2,
        document_page_number=1,
    )
    assert ledger.register_started(a1).accepted
    assert ledger.register_terminal(a1, "timed_out").accepted
    assert ledger.register_started(a2).accepted
    assert ledger.is_stale_attempt(
        a1, current_attempt_number=2, current_page=1, current_generation=1
    )


def test_heartbeat_does_not_advance_progress() -> None:
    snap = ProgressSnapshot(document_id="doc_1")
    snap.begin_operation("paddle_ocr_pipeline")
    before = snap.overall_percent
    snap.bump_overall(45.0)
    mid = snap.overall_percent
    snap.mark_heartbeat()
    assert snap.overall_percent == mid
    assert mid >= before


def test_overall_never_exceeds_65() -> None:
    snap = ProgressSnapshot()
    snap.bump_overall(100.0)
    assert snap.overall_percent == OVERALL_CAP


def test_native_only_workflow_no_fake_ocr() -> None:
    snap = ProgressSnapshot(document_id="doc_n", document_pages_total=8)
    for page in range(1, 9):
        snap.set_native_only_progress(
            pages_completed=page,
            pages_total=8,
            document_page_number=page,
        )
    snap.set_visual_summary_progress()
    snap.set_visual_authority_progress()
    snap.set_visual_complete()
    assert snap.overall_percent == OVERALL_CAP
    assert snap.history == [] or all(
        entry.get("operation") != "full_ocr_primary" for entry in snap.history
    )


def test_sparse_ocr_pages_use_selected_fraction() -> None:
    snap = ProgressSnapshot(document_id="doc_s", document_pages_total=104)
    snap.set_visual_selection_complete(pages_selected=2)
    snap.begin_page(20, selected_page_index=1, selected_pages_total=2)
    snap.set_visual_page_progress(
        pages_completed=0,
        pages_selected=2,
        page_number=20,
        page_percent=PAGE_PUBLISHED,
        selected_page_index=1,
        document_pages_total=104,
    )
    after_first = snap.overall_percent
    snap.set_visual_page_progress(
        pages_completed=1,
        pages_selected=2,
        page_number=20,
        page_percent=PAGE_PUBLISHED,
        include_page_in_fraction=False,
        selected_page_index=1,
        document_pages_total=104,
    )
    snap.begin_page(22, selected_page_index=2, selected_pages_total=2)
    snap.set_visual_page_progress(
        pages_completed=1,
        pages_selected=2,
        page_number=22,
        page_percent=PAGE_PUBLISHED,
        selected_page_index=2,
        document_pages_total=104,
    )
    assert snap.document_page_number == 22
    assert snap.selected_page_index == 2
    assert snap.overall_percent >= after_first
    snap.set_visual_summary_progress()
    snap.set_visual_authority_progress()
    snap.set_visual_complete()
    assert snap.overall_percent == OVERALL_CAP


def test_deadlines_remain_separated() -> None:
    snap = ProgressSnapshot()
    now = snap.job_started_at
    snap.document_deadline_mono = now + 100
    snap.page_deadline_mono = now + 40
    snap.operation_deadline_mono = now + 20
    snap._refresh_deadlines(now=now)
    assert snap.document_deadline_remaining_seconds == pytest.approx(100, abs=0.5)
    assert snap.page_deadline_remaining_seconds == pytest.approx(40, abs=0.5)
    assert snap.operation_deadline_remaining_seconds == pytest.approx(20, abs=0.5)
    assert snap.deadline_remaining_seconds == snap.operation_deadline_remaining_seconds


def test_slow_warning_resets_on_operation_change() -> None:
    snap = ProgressSnapshot(document_id="doc_1")
    snap.slow_warning_threshold_seconds = 0.01
    assert snap.begin_operation("paddle_ocr_pipeline")
    import time

    time.sleep(0.02)
    snap.mark_heartbeat()
    assert snap.slow_warning_status is SlowWarningStatus.ACTIVE
    assert snap.terminal_operation(OperationStatus.COMPLETED)
    assert snap.slow_warning_status is SlowWarningStatus.RESOLVED
    assert snap.begin_operation("visual_page_render", attempt_number=1)
    assert snap.slow_warning_status is SlowWarningStatus.INACTIVE
    assert snap.operation_elapsed_seconds < 0.05


def test_full_ocr_completed_cannot_exceed_selected() -> None:
    with pytest.raises(ValidationError):
        ProgressEvent(
            event_id="evt_2",
            event_sequence=2,
            event=ProgressEventType.DOCUMENT_FULL_OCR_PRIMARY_COMPLETED,
            session_id="ses_1",
            timestamp=__import__("datetime").datetime.now(__import__("datetime").UTC),
            full_ocr_pages_selected=1,
            full_ocr_pages_completed=2,
        )

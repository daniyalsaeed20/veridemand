"""Progress lifecycle coverage for Correction 5 OCR quality operations."""

from __future__ import annotations

from backend.app.contracts.progress import ProgressEventType
from backend.app.processing.progress_model import OperationStatus, ProgressSnapshot


def test_quality_evaluation_and_selection_lifecycle_is_valid() -> None:
    snap = ProgressSnapshot()
    assert snap.begin_operation("full_ocr_primary")
    assert snap.terminal_operation(OperationStatus.COMPLETED)

    assert snap.begin_operation("full_ocr_quality_evaluation")
    assert snap.operation == "full_ocr_quality_evaluation"
    assert snap.terminal_operation(OperationStatus.COMPLETED)

    assert snap.begin_operation("full_ocr_fallback")
    assert snap.terminal_operation(OperationStatus.COMPLETED)

    assert snap.begin_operation("full_ocr_result_selection")
    assert snap.terminal_operation(OperationStatus.COMPLETED)


def test_quality_event_types_are_registered() -> None:
    assert (
        ProgressEventType.DOCUMENT_FULL_OCR_QUALITY_EVALUATION_STARTED.value
        == "document.full_ocr_quality_evaluation_started"
    )
    assert (
        ProgressEventType.DOCUMENT_FULL_OCR_RESULT_SELECTION_COMPLETED.value
        == "document.full_ocr_result_selection_completed"
    )


def test_quality_terminal_leaves_operation_completed() -> None:
    snap = ProgressSnapshot()
    snap.begin_operation("full_ocr_quality_evaluation")
    assert snap.terminal_operation(OperationStatus.COMPLETED)
    assert snap.operation_status is OperationStatus.COMPLETED
    assert snap.operation == "full_ocr_quality_evaluation"

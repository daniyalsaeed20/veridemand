"""Checkpoint C — scheduler lifecycle event publishing helpers."""

from __future__ import annotations

from backend.app.contracts.progress import ProgressEventType
from backend.app.processing.fair_scheduler import (
    FairDocumentScheduler,
    SchedulerConfig,
    SchedulingDocumentState,
)
from backend.tests.test_fair_scheduler import _make_units, _sched


def test_cancel_ready_leaves_terminal_state() -> None:
    sched = _sched()
    sched.admit_document("d1", "s1", _make_units("d1", "s1", [1, 2]))
    result = sched.cancel_document("d1")
    assert result is not None
    assert result.state == SchedulingDocumentState.CANCELLED
    assert sched.get_document("d1") is not None


def test_cancel_checkpointed_leaves_terminal_state() -> None:
    sched = _sched(quantum=1)
    sched.admit_document("d1", "s1", _make_units("d1", "s1", [1, 2, 3]))
    unit = sched.next_work_unit()
    assert unit is not None
    sched.complete_work_unit(unit[1].work_unit_id)
    # After quantum=1, document should have yielded back to ready/checkpointed path
    doc = sched.get_document("d1")
    assert doc is not None
    if doc.state == SchedulingDocumentState.READY:
        doc.transition_to(SchedulingDocumentState.RUNNING)
        doc.transition_to(SchedulingDocumentState.CHECKPOINTED)
    result = sched.cancel_document("d1")
    assert result is not None
    assert result.state == SchedulingDocumentState.CANCELLED


def test_scheduler_lifecycle_event_types_defined() -> None:
    expected = {
        "scheduler.document_admitted",
        "scheduler.document_ready",
        "scheduler.turn_started",
        "scheduler.quantum_completed",
        "scheduler.document_yielded",
        "scheduler.document_checkpointed",
        "scheduler.priority_changed",
        "scheduler.document_resumed",
        "scheduler.document_terminal",
    }
    values = {member.value for member in ProgressEventType if member.value.startswith("scheduler.")}
    assert values == expected


def test_fail_work_unit_retryable_preserves_remaining() -> None:
    sched = FairDocumentScheduler(SchedulerConfig(page_quantum=2, enabled=True))
    sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))
    claimed = sched.next_work_unit()
    assert claimed is not None
    failed = sched.fail_work_unit(claimed[1].work_unit_id, retryable=True)
    assert failed is not None
    doc = sched.get_document("d1")
    assert doc is not None
    assert doc.remaining_work == 1

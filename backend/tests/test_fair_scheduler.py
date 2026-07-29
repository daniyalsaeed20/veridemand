"""Tests for the fair document scheduler (Correction 7)."""

from __future__ import annotations

import time
from typing import Any

import pytest

from backend.app.processing.fair_scheduler import (
    FairDocumentScheduler,
    InvalidTransitionError,
    PriorityClass,
    SchedulerConfig,
    SchedulerWorkUnit,
    SchedulingDocumentState,
    WorkClass,
    WorkUnitStatus,
    _new_work_unit_id,
    classify_priority,
)


def _make_units(
    doc_id: str,
    session_id: str,
    pages: list[int],
    *,
    work_class: WorkClass = WorkClass.FULL_OCR_PAGE,
) -> list[SchedulerWorkUnit]:
    return [
        SchedulerWorkUnit(
            work_unit_id=_new_work_unit_id(),
            session_id=session_id,
            document_id=doc_id,
            route="full_visual_ocr",
            work_class=work_class,
            document_page_number=p,
            document_pages_total=max(pages),
            selected_page_index=i + 1,
            selected_pages_total=len(pages),
        )
        for i, p in enumerate(pages)
    ]


def _sched(*, quantum: int = 2, enabled: bool = True, **kw: Any) -> FairDocumentScheduler:
    return FairDocumentScheduler(SchedulerConfig(page_quantum=quantum, enabled=enabled, **kw))


class TestAdmission:
    def test_deterministic_admission_order(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1, 2, 3]))
        sched.admit_document("d2", "s2", _make_units("d2", "s2", [1, 2]))
        d1 = sched.get_document("d1")
        d2 = sched.get_document("d2")
        assert d1 is not None and d2 is not None
        assert d1.admitted_sequence < d2.admitted_sequence

    def test_duplicate_admission_rejected(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))
        with pytest.raises(ValueError, match="already admitted"):
            sched.admit_document("d1", "s1", _make_units("d1", "s1", [2]))

    def test_admission_on_closed_scheduler(self) -> None:
        sched = _sched()
        sched.close()
        with pytest.raises(RuntimeError, match="closed"):
            sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))


class TestRoundRobin:
    def test_round_robin_turns(self) -> None:
        sched = _sched(quantum=1)
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1, 2, 3]))
        sched.admit_document("d2", "s2", _make_units("d2", "s2", [1, 2]))

        r1 = sched.next_work_unit()
        assert r1 is not None
        doc1, u1 = r1
        sched.complete_work_unit(u1.work_unit_id)
        if sched.should_yield(doc1.document_id):
            sched.yield_document(doc1.document_id)

        r2 = sched.next_work_unit()
        assert r2 is not None
        doc2, _u2 = r2
        assert doc2.document_id != doc1.document_id

    def test_page_quantum_enforced(self) -> None:
        sched = _sched(quantum=2)
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1, 2, 3, 4]))
        sched.admit_document("d2", "s2", _make_units("d2", "s2", [1, 2, 3, 4]))

        first_doc_id: str | None = None
        for _ in range(2):
            r = sched.next_work_unit()
            assert r is not None
            first_doc_id = first_doc_id or r[0].document_id
            sched.complete_work_unit(r[1].work_unit_id)
        assert first_doc_id is not None
        nxt = sched.next_work_unit()
        assert nxt is not None
        assert nxt[0].document_id != first_doc_id

    def test_no_page_processed_twice(self) -> None:
        sched = _sched(quantum=1)
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1, 2]))
        seen_pages: set[int] = set()
        while sched.has_work():
            r = sched.next_work_unit()
            if r is None:
                break
            _doc, unit = r
            assert unit.document_page_number not in seen_pages
            seen_pages.add(unit.document_page_number)
            sched.complete_work_unit(unit.work_unit_id)

    def test_completed_checkpoint_not_repeated(self) -> None:
        sched = _sched(quantum=1)
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1, 2, 3]))
        sched.admit_document("d2", "s2", _make_units("d2", "s2", [1]))

        r1 = sched.next_work_unit()
        assert r1 is not None
        sched.complete_work_unit(r1[1].work_unit_id)
        sched.yield_document("d1")

        r2 = sched.next_work_unit()
        assert r2 is not None
        assert r2[0].document_id == "d2"
        sched.complete_work_unit(r2[1].work_unit_id)

        r3 = sched.next_work_unit()
        assert r3 is not None
        assert r3[0].document_id == "d1"
        assert r3[1].document_page_number != r1[1].document_page_number


class TestPriorityClassification:
    def test_short_priority(self) -> None:
        assert classify_priority(2) == PriorityClass.INTERACTIVE_SHORT

    def test_normal_priority(self) -> None:
        assert classify_priority(10) == PriorityClass.NORMAL

    def test_large_priority(self) -> None:
        assert classify_priority(25) == PriorityClass.LARGE_BACKGROUND

    def test_short_threshold_configurable(self) -> None:
        assert classify_priority(5, short_threshold=5) == PriorityClass.INTERACTIVE_SHORT


class TestStarvationPrevention:
    def test_aging_increases_priority(self) -> None:
        sched = _sched(quantum=1, aging_interval_seconds=0.01)
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1, 2]))
        doc = sched.get_document("d1")
        assert doc is not None
        time.sleep(0.05)
        sched._apply_aging()
        assert doc.aging_adjustment > 0

    def test_max_consecutive_turns(self) -> None:
        sched = _sched(quantum=1, max_consecutive_turns=2)
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1, 2, 3, 4]))
        sched.admit_document("d2", "s2", _make_units("d2", "s2", [1, 2, 3, 4]))

        ids: list[str] = []
        for _ in range(6):
            r = sched.next_work_unit()
            assert r is not None
            ids.append(r[0].document_id)
            sched.complete_work_unit(r[1].work_unit_id)
        assert "d1" in ids
        assert "d2" in ids


class TestMoveAheadBehind:
    def test_move_ahead(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))
        sched.admit_document("d2", "s2", _make_units("d2", "s2", [1]))
        assert sched.move_ahead("d2")
        r = sched.next_work_unit()
        assert r is not None
        assert r[0].document_id == "d2"

    def test_move_behind(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))
        sched.admit_document("d2", "s2", _make_units("d2", "s2", [1]))
        assert sched.move_behind("d1")
        r = sched.next_work_unit()
        assert r is not None
        assert r[0].document_id == "d2"

    def test_restore_default_priority(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1, 2]))
        doc = sched.get_document("d1")
        assert doc is not None
        doc.aging_adjustment = 5
        doc.effective_priority = 0
        sched.restore_default_priority("d1")
        assert doc.aging_adjustment == 0

    def test_move_terminal_document_rejected(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))
        sched.complete_document("d1")
        assert not sched.move_ahead("d1")


class TestCancellation:
    def test_cancel_ready(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1, 2]))
        result = sched.cancel_document("d1")
        assert result is not None
        assert result.state == SchedulingDocumentState.CANCELLED
        assert result.remaining_work == 0
        assert sched.next_work_unit() is None

    def test_cancel_checkpointed(self) -> None:
        sched = _sched(quantum=1)
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1, 2, 3]))
        r = sched.next_work_unit()
        assert r is not None
        sched.complete_work_unit(r[1].work_unit_id)
        sched.yield_document("d1")
        result = sched.cancel_document("d1")
        assert result is not None
        assert result.state == SchedulingDocumentState.CANCELLED

    def test_cancel_running(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1, 2]))
        r = sched.next_work_unit()
        assert r is not None
        result = sched.cancel_document("d1")
        assert result is not None
        assert result.state == SchedulingDocumentState.CANCELLED

    def test_cancel_does_not_affect_others(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))
        sched.admit_document("d2", "s2", _make_units("d2", "s2", [1]))
        sched.cancel_document("d1")
        r = sched.next_work_unit()
        assert r is not None
        assert r[0].document_id == "d2"


class TestWorkerLossAndRetry:
    def test_fail_retryable(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))
        r = sched.next_work_unit()
        assert r is not None
        unit = sched.fail_work_unit(r[1].work_unit_id, retryable=True)
        assert unit is not None
        assert unit.status == WorkUnitStatus.RETRYING
        assert unit.attempt_number == 2

    def test_fail_not_retryable(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))
        r = sched.next_work_unit()
        assert r is not None
        unit = sched.fail_work_unit(r[1].work_unit_id, retryable=False)
        assert unit is not None
        assert unit.status == WorkUnitStatus.FAILED

    def test_bounded_retry(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))
        r = sched.next_work_unit()
        assert r is not None
        sched.fail_work_unit(r[1].work_unit_id, retryable=True)
        r2 = sched.next_work_unit()
        assert r2 is not None
        unit = sched.fail_work_unit(r2[1].work_unit_id, retryable=True)
        assert unit is not None
        assert unit.status == WorkUnitStatus.FAILED


class TestFailureIsolation:
    def test_document_failure_does_not_stop_scheduler(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))
        sched.admit_document("d2", "s2", _make_units("d2", "s2", [1]))
        sched.fail_document("d1")
        r = sched.next_work_unit()
        assert r is not None
        assert r[0].document_id == "d2"


class TestStateMachine:
    def test_invalid_transition_rejected(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))
        doc = sched.get_document("d1")
        assert doc is not None
        with pytest.raises(InvalidTransitionError):
            doc.transition_to(SchedulingDocumentState.CHECKPOINTED)

    def test_completed_cannot_return_to_ready(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))
        r = sched.next_work_unit()
        assert r is not None
        sched.complete_work_unit(r[1].work_unit_id)
        sched.complete_document("d1")
        doc = sched.get_document("d1")
        assert doc is not None
        with pytest.raises(InvalidTransitionError):
            doc.transition_to(SchedulingDocumentState.READY)


class TestShutdown:
    def test_close_prevents_new_work(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))
        sched.close()
        assert sched.next_work_unit() is None

    def test_close_prevents_admission(self) -> None:
        sched = _sched()
        sched.close()
        with pytest.raises(RuntimeError):
            sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))


class TestSnapshot:
    def test_snapshot_fields(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))
        snap = sched.snapshot()
        assert snap["scheduler_enabled"] is True
        assert snap["ready_document_count"] == 1
        assert snap["turn_number"] == 0

    def test_snapshot_after_turn(self) -> None:
        sched = _sched()
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1]))
        r = sched.next_work_unit()
        assert r is not None
        snap = sched.snapshot()
        assert snap["turn_number"] == 1
        assert snap["active_document_id"] == "d1"


class TestDisabledMode:
    def test_disabled_no_yield(self) -> None:
        sched = _sched(enabled=False)
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1, 2, 3]))
        sched.admit_document("d2", "s2", _make_units("d2", "s2", [1]))
        for _ in range(3):
            r = sched.next_work_unit()
            if r is None:
                break
            sched.complete_work_unit(r[1].work_unit_id)
            assert not sched.should_yield("d1")


class TestNativeBypass:
    def test_native_document_has_no_heavy_units(self) -> None:
        sched = _sched()
        native_units = _make_units(
            "d1",
            "s1",
            [1, 2, 3],
            work_class=WorkClass.NATIVE_DOCUMENT_WORK,
        )
        sched.admit_document("d1", "s1", native_units)
        doc = sched.get_document("d1")
        assert doc is not None
        assert doc.priority_class == PriorityClass.INTERACTIVE_SHORT


class TestProgressMonotonicity:
    def test_progress_monotonic_across_yields(self) -> None:
        sched = _sched(quantum=1)
        sched.admit_document("d1", "s1", _make_units("d1", "s1", [1, 2, 3]))
        sched.admit_document("d2", "s2", _make_units("d2", "s2", [1]))

        completed_pages: list[int] = []
        while sched.has_work():
            r = sched.next_work_unit()
            if r is None:
                break
            doc, unit = r
            sched.complete_work_unit(unit.work_unit_id)
            if doc.document_id == "d1":
                completed_pages.append(unit.document_page_number)
            if sched.should_yield(doc.document_id):
                sched.yield_document(doc.document_id)

        assert completed_pages == sorted(completed_pages)


class TestThreeEqualDocuments:
    def test_deterministic_round_robin(self) -> None:
        sched = _sched(quantum=1)
        for name in ("d1", "d2", "d3"):
            sched.admit_document(name, f"s_{name}", _make_units(name, f"s_{name}", [1, 2]))

        turn_order: list[str] = []
        while sched.has_work():
            r = sched.next_work_unit()
            if r is None:
                break
            doc, unit = r
            turn_order.append(doc.document_id)
            sched.complete_work_unit(unit.work_unit_id)
            if sched.should_yield(doc.document_id):
                sched.yield_document(doc.document_id)

        assert set(turn_order) == {"d1", "d2", "d3"}
        for doc_id in ("d1", "d2", "d3"):
            final_doc = sched.get_document(doc_id)
            assert final_doc is not None
            assert final_doc.remaining_work == 0

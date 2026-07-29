"""Correction 7 synthetic fairness workloads A/C/H/K (opaque, no private files)."""

from __future__ import annotations

from backend.app.processing.fair_scheduler import (
    FairDocumentScheduler,
    SchedulerConfig,
    SchedulingDocumentState,
)
from backend.tests.test_fair_scheduler import _make_units, _sched


def test_workload_a_small_receives_turn_before_large_finishes() -> None:
    """A: 12-page OCR + 2-page OCR — small document gets a turn early."""
    sched = _sched(quantum=2)
    sched.admit_document("large", "s1", _make_units("large", "s1", list(range(1, 13))))
    sched.admit_document("small", "s2", _make_units("small", "s2", [1, 2]))

    first = sched.next_work_unit()
    assert first is not None
    # Interactive-short (small) outranks large_background.
    assert first[0].document_id == "small"
    sched.complete_work_unit(first[1].work_unit_id)
    second = sched.next_work_unit()
    assert second is not None
    assert second[0].document_id == "small"


def test_workload_c_equal_docs_round_robin() -> None:
    """C: three equal OCR documents — deterministic round-robin, no starvation."""
    sched = _sched(quantum=1)
    for name in ("a", "b", "c"):
        sched.admit_document(name, f"s_{name}", _make_units(name, f"s_{name}", [1, 2]))

    order: list[str] = []
    for _ in range(6):
        claimed = sched.next_work_unit()
        assert claimed is not None
        order.append(claimed[0].document_id)
        sched.complete_work_unit(claimed[1].work_unit_id)
        if sched.should_yield(claimed[0].document_id):
            sched.yield_document(claimed[0].document_id)

    assert set(order) == {"a", "b", "c"}
    assert order.count("a") == 2
    assert order.count("b") == 2
    assert order.count("c") == 2


def test_workload_h_cancel_ready_before_worker() -> None:
    """H: cancellation while ready — clean removal, no active work unit."""
    sched = _sched()
    sched.admit_document("d1", "s1", _make_units("d1", "s1", [1, 2, 3]))
    assert sched.active_work_unit is None
    result = sched.cancel_document("d1")
    assert result is not None
    assert result.state is SchedulingDocumentState.CANCELLED
    assert sched.active_work_unit is None
    assert sched.next_work_unit() is None


def test_workload_k_move_ahead_changes_next_turn() -> None:
    """K: priority move-ahead — next turn reflects the change."""
    sched = FairDocumentScheduler(
        SchedulerConfig(page_quantum=1, enabled=True, short_document_heavy_page_threshold=1)
    )
    # Force both into NORMAL by using 5 pages each (> threshold 1, <= 20).
    sched.admit_document("first", "s1", _make_units("first", "s1", [1, 2, 3, 4, 5]))
    sched.admit_document("second", "s2", _make_units("second", "s2", [1, 2, 3, 4, 5]))
    assert sched.move_ahead("second") is True
    claimed = sched.next_work_unit()
    assert claimed is not None
    assert claimed[0].document_id == "second"

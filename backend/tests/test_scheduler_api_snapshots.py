"""Checkpoint D — scheduler API and session snapshot wiring."""

from __future__ import annotations

import pytest

from backend.app.contracts.identifiers import new_document_id
from backend.app.contracts.scheduling import PriorityChangeResponse, SchedulerSnapshot
from backend.app.processing.fair_scheduler import FairDocumentScheduler, SchedulerConfig
from backend.app.sessions.service import build_session_snapshot
from backend.app.settings.config import Settings
from backend.tests.conftest import build_runtime


def test_scheduler_snapshot_model_accepts_runtime_dict() -> None:
    snap = SchedulerSnapshot(
        scheduler_enabled=True,
        scheduler_policy_version="correction7-v1",
        active_document_id=None,
        active_work_unit_id=None,
        ready_document_count=2,
        checkpointed_document_count=1,
        turn_number=4,
    )
    assert snap.ready_document_count == 2
    assert snap.turn_number == 4


def test_priority_change_response_shape() -> None:
    body = PriorityChangeResponse(
        document_id=new_document_id(),
        action="move_ahead",
        success=True,
        message="ok",
    )
    assert body.success is True
    assert body.action == "move_ahead"


@pytest.mark.asyncio
async def test_build_session_snapshot_fills_queue_scheduler_fields(
    tmp_path: object,
) -> None:
    settings = Settings(temp_root=tmp_path)
    registry, _queue, _store = build_runtime(settings)
    session = await registry.create()
    sched = FairDocumentScheduler(SchedulerConfig(enabled=True, page_quantum=2))
    snapshot = build_session_snapshot(session, settings, scheduler=sched)
    assert snapshot.queue.scheduler_enabled is True
    assert snapshot.queue.scheduler_ready_count == 0
    assert snapshot.queue.scheduler_turn_number == 0

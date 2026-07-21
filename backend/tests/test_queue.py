from __future__ import annotations

import pytest

from backend.app.contracts.identifiers import new_document_id, new_job_id, new_session_id
from backend.app.processing.models import ProcessingJob
from backend.app.processing.queue import InMemoryJobQueue, QueueClosedError


def _job() -> ProcessingJob:
    return ProcessingJob(
        job_id=new_job_id(),
        session_id=new_session_id(),
        document_id=new_document_id(),
    )


async def test_enqueue_assigns_one_based_positions() -> None:
    queue = InMemoryJobQueue()
    first, second, third = _job(), _job(), _job()
    for job in (first, second, third):
        await queue.enqueue(job)

    assert first.queue_position == 1
    assert second.queue_position == 2
    assert third.queue_position == 3
    assert await queue.position(second.job_id) == 2


async def test_get_returns_fifo_order() -> None:
    queue = InMemoryJobQueue()
    jobs = [_job() for _ in range(3)]
    for job in jobs:
        await queue.enqueue(job)

    order = [(await queue.get()).job_id for _ in range(3)]
    assert order == [job.job_id for job in jobs]


async def test_cancel_removes_and_recalculates_positions() -> None:
    queue = InMemoryJobQueue()
    first, second, third = _job(), _job(), _job()
    for job in (first, second, third):
        await queue.enqueue(job)

    assert await queue.cancel(second.job_id) is True
    assert third.queue_position == 2
    assert await queue.position(second.job_id) is None


async def test_get_skips_cancelled_tokens() -> None:
    queue = InMemoryJobQueue()
    first, second = _job(), _job()
    await queue.enqueue(first)
    await queue.enqueue(second)

    await queue.cancel(first.job_id)
    nxt = await queue.get()
    assert nxt.job_id == second.job_id


async def test_cancel_unknown_job_returns_false() -> None:
    queue = InMemoryJobQueue()
    assert await queue.cancel("job_" + "0" * 32) is False


async def test_enqueue_after_close_raises() -> None:
    queue = InMemoryJobQueue()
    await queue.close()
    assert queue.closed is True
    with pytest.raises(QueueClosedError):
        await queue.enqueue(_job())

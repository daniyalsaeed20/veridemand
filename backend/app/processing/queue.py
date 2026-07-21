"""In-memory FIFO job queue.

Backed by a single ``asyncio.Queue`` of job-id tokens plus a protected ordered
pending index used to compute 1-based queue positions. Cancelled queued jobs are
removed from the pending index and marked so the worker skips their leftover
token safely; private ``asyncio.Queue`` internals are never accessed. This is a
future-facing ``JobQueue`` so later phases can swap the implementation.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from backend.app.processing.models import ProcessingJob


class QueueClosedError(RuntimeError):
    """Raised when enqueuing onto a closed queue."""


class JobQueue(Protocol):
    async def enqueue(self, job: ProcessingJob) -> None: ...
    async def cancel(self, job_id: str) -> bool: ...
    async def get(self) -> ProcessingJob: ...
    async def task_done(self, job_id: str) -> None: ...
    async def position(self, job_id: str) -> int | None: ...
    async def close(self) -> None: ...


class InMemoryJobQueue:
    """A single-process FIFO queue with cancellable, position-tracked jobs."""

    def __init__(self) -> None:
        self._tokens: asyncio.Queue[str] = asyncio.Queue()
        self._jobs: dict[str, ProcessingJob] = {}
        self._pending: list[str] = []
        self._cancelled: set[str] = set()
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def _recalculate_positions(self) -> None:
        for index, job_id in enumerate(self._pending):
            job = self._jobs.get(job_id)
            if job is not None:
                job.queue_position = index + 1

    async def enqueue(self, job: ProcessingJob) -> None:
        async with self._lock:
            if self._closed:
                raise QueueClosedError("The processing queue is closed.")
            self._jobs[job.job_id] = job
            self._pending.append(job.job_id)
            self._recalculate_positions()
        await self._tokens.put(job.job_id)

    async def cancel(self, job_id: str) -> bool:
        """Cancel a still-queued job. Returns True if it was pending."""

        async with self._lock:
            if job_id in self._pending:
                self._pending.remove(job_id)
                self._cancelled.add(job_id)
                job = self._jobs.get(job_id)
                if job is not None:
                    job.queue_position = None
                self._recalculate_positions()
                return True
            return False

    async def get(self) -> ProcessingJob:
        """Return the next non-cancelled job, skipping cancelled tokens."""

        while True:
            token = await self._tokens.get()
            async with self._lock:
                if token in self._cancelled:
                    self._cancelled.discard(token)
                    self._tokens.task_done()
                    continue
                job = self._jobs.get(token)
                if token in self._pending:
                    self._pending.remove(token)
                if job is not None:
                    job.queue_position = None
                self._recalculate_positions()
            if job is None:
                self._tokens.task_done()
                continue
            return job

    async def task_done(self, job_id: str) -> None:
        async with self._lock:
            self._jobs.pop(job_id, None)
        self._tokens.task_done()

    async def position(self, job_id: str) -> int | None:
        async with self._lock:
            if job_id in self._pending:
                return self._pending.index(job_id) + 1
            return None

    async def close(self) -> None:
        async with self._lock:
            self._closed = True

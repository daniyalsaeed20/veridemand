"""Periodic cleanup worker.

Runs ``CleanupService.sweep_once`` on a fixed interval. The interval wait is
implemented as a bounded wait on a stop event so shutdown is prompt and no sweep
overlaps another.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from backend.app.cleanup.service import CleanupService

logger = logging.getLogger("veridemand.cleanup")


class CleanupWorker:
    """Drives periodic TTL cleanup sweeps."""

    def __init__(self, cleanup: CleanupService, interval_seconds: float) -> None:
        self._cleanup = cleanup
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="cleanup-worker")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval)
            except TimeoutError:
                pass  # interval elapsed: run a sweep
            else:
                break  # stop requested
            try:
                await self._cleanup.sweep_once()
            except Exception:
                logger.exception("Periodic cleanup sweep failed.")

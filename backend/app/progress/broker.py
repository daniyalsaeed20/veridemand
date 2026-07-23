"""Per-session Server-Sent Events broker with bounded replay and resync.

One broker exists per session. It allocates a monotonic per-session event
sequence, validates every event through the strict ``ProgressEvent`` model,
retains a bounded replay history, and delivers to bounded subscriber queues. A
slow subscriber that overflows its queue is signalled to resynchronise and then
closed, rather than growing memory without bound or silently dropping events.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from backend.app.contracts.documents import DocumentStatus
from backend.app.contracts.identifiers import format_event_id
from backend.app.contracts.jobs import JobStatus
from backend.app.contracts.progress import ProgressEvent, ProgressEventType
from backend.app.progress.models import BrokerClosedError, ConnectResult, Subscriber


def _parse_event_sequence(last_event_id: str | None) -> int | None:
    if last_event_id is None:
        return None
    value = last_event_id.strip()
    if value.startswith("evt_"):
        value = value[len("evt_") :]
    if not value.isdigit():
        return None
    try:
        return int(value)
    except ValueError:
        return None


class EventBroker:
    """A bounded, replayable event stream for a single session."""

    def __init__(self, session_id: str, *, replay_max: int, subscriber_queue_size: int) -> None:
        self._session_id = session_id
        self._replay: deque[ProgressEvent] = deque(maxlen=replay_max)
        self._sequence = 0
        self._subscribers: set[Subscriber] = set()
        self._closed = False
        self._lock = asyncio.Lock()
        self._subscriber_queue_size = subscriber_queue_size

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def current_sequence(self) -> int:
        return self._sequence

    def recent_events(self, limit: int) -> list[ProgressEvent]:
        """Return up to ``limit`` most-recent retained events (oldest first)."""

        if limit <= 0:
            return []
        events = list(self._replay)
        return events[-limit:]

    def _build_event(
        self,
        sequence: int,
        event: ProgressEventType,
        *,
        document_id: str | None,
        job_id: str | None,
        stage: str | None,
        percent: int | None,
        message: str | None,
        queue_position: int | None,
        document_status: DocumentStatus | None,
        job_status: JobStatus | None,
        canonicalisation_method: str | None,
        canonical_page_count: int | None,
        canonical_status: str | None,
        page_number: int | None = None,
        pages_completed: int | None = None,
        pages_total: int | None = None,
        decision: str | None = None,
        source_mode: str | None = None,
        native_trust_score: float | None = None,
        reason_codes: list[str] | None = None,
        overall_percent: float | None = None,
        major_phase: str | None = None,
        major_phase_percent: float | None = None,
        page_percent: float | None = None,
        operation: str | None = None,
        operation_status: str | None = None,
        progress_kind: str | None = None,
        elapsed_seconds: float | None = None,
        stage_elapsed_seconds: float | None = None,
        deadline_remaining_seconds: float | None = None,
        worker_pid: int | None = None,
        worker_generation: int | None = None,
        worker_restart_count: int | None = None,
        attempt_number: int | None = None,
        max_attempts: int | None = None,
        reason_code: str | None = None,
    ) -> ProgressEvent:
        return ProgressEvent(
            event_id=format_event_id(sequence),
            event_sequence=sequence,
            event=event,
            session_id=self._session_id,
            document_id=document_id,
            job_id=job_id,
            timestamp=datetime.now(UTC),
            stage=stage,
            percent=percent,
            page_number=page_number,
            pages_completed=pages_completed,
            pages_total=pages_total,
            message=message,
            queue_position=queue_position,
            document_status=document_status,
            job_status=job_status,
            canonicalisation_method=canonicalisation_method,
            canonical_page_count=canonical_page_count,
            canonical_status=canonical_status,
            decision=decision,
            source_mode=source_mode,
            native_trust_score=native_trust_score,
            reason_codes=reason_codes,
            overall_percent=overall_percent,
            major_phase=major_phase,
            major_phase_percent=major_phase_percent,
            page_percent=page_percent,
            operation=operation,
            operation_status=operation_status,
            progress_kind=progress_kind,
            elapsed_seconds=elapsed_seconds,
            stage_elapsed_seconds=stage_elapsed_seconds,
            deadline_remaining_seconds=deadline_remaining_seconds,
            worker_pid=worker_pid,
            worker_generation=worker_generation,
            worker_restart_count=worker_restart_count,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            reason_code=reason_code,
        )

    async def publish(
        self,
        event: ProgressEventType,
        *,
        document_id: str | None = None,
        job_id: str | None = None,
        stage: str | None = None,
        percent: int | None = None,
        message: str | None = None,
        queue_position: int | None = None,
        document_status: DocumentStatus | None = None,
        job_status: JobStatus | None = None,
        canonicalisation_method: str | None = None,
        canonical_page_count: int | None = None,
        canonical_status: str | None = None,
        page_number: int | None = None,
        pages_completed: int | None = None,
        pages_total: int | None = None,
        decision: str | None = None,
        source_mode: str | None = None,
        native_trust_score: float | None = None,
        reason_codes: list[str] | None = None,
        overall_percent: float | None = None,
        major_phase: str | None = None,
        major_phase_percent: float | None = None,
        page_percent: float | None = None,
        operation: str | None = None,
        operation_status: str | None = None,
        progress_kind: str | None = None,
        elapsed_seconds: float | None = None,
        stage_elapsed_seconds: float | None = None,
        deadline_remaining_seconds: float | None = None,
        worker_pid: int | None = None,
        worker_generation: int | None = None,
        worker_restart_count: int | None = None,
        attempt_number: int | None = None,
        max_attempts: int | None = None,
        reason_code: str | None = None,
    ) -> ProgressEvent:
        """Allocate a sequence, record, and deliver an event to subscribers."""

        async with self._lock:
            if self._closed:
                raise BrokerClosedError("Cannot publish to a closed broker.")
            self._sequence += 1
            progress = self._build_event(
                self._sequence,
                event,
                document_id=document_id,
                job_id=job_id,
                stage=stage,
                percent=percent,
                message=message,
                queue_position=queue_position,
                document_status=document_status,
                job_status=job_status,
                canonicalisation_method=canonicalisation_method,
                canonical_page_count=canonical_page_count,
                canonical_status=canonical_status,
                page_number=page_number,
                pages_completed=pages_completed,
                pages_total=pages_total,
                decision=decision,
                source_mode=source_mode,
                native_trust_score=native_trust_score,
                reason_codes=reason_codes,
                overall_percent=overall_percent,
                major_phase=major_phase,
                major_phase_percent=major_phase_percent,
                page_percent=page_percent,
                operation=operation,
                operation_status=operation_status,
                progress_kind=progress_kind,
                elapsed_seconds=elapsed_seconds,
                stage_elapsed_seconds=stage_elapsed_seconds,
                deadline_remaining_seconds=deadline_remaining_seconds,
                worker_pid=worker_pid,
                worker_generation=worker_generation,
                worker_restart_count=worker_restart_count,
                attempt_number=attempt_number,
                max_attempts=max_attempts,
                reason_code=reason_code,
            )
            self._replay.append(progress)
            for subscriber in self._subscribers:
                if subscriber.closed:
                    continue
                try:
                    subscriber.queue.put_nowait(progress)
                except asyncio.QueueFull:
                    subscriber.overflow = True
                    subscriber.signal.set()
        return progress

    async def connect(self, last_event_id: str | None) -> ConnectResult:
        """Register a subscriber and compute any replay/resync requirement."""

        async with self._lock:
            if self._closed:
                raise BrokerClosedError("Broker is closed.")
            subscriber = Subscriber(self._subscriber_queue_size)
            self._subscribers.add(subscriber)

            requested = _parse_event_sequence(last_event_id)
            if requested is None and last_event_id is None:
                return ConnectResult(subscriber=subscriber)
            if requested is None:
                # Malformed Last-Event-ID -> force a full resync.
                return ConnectResult(subscriber=subscriber, resync_required=True)

            if requested == self._sequence:
                return ConnectResult(subscriber=subscriber)
            if requested > self._sequence:
                return ConnectResult(subscriber=subscriber, resync_required=True)
            if not self._replay:
                return ConnectResult(subscriber=subscriber, resync_required=True)

            earliest = self._replay[0].event_sequence
            if requested >= earliest - 1:
                replay = [e for e in self._replay if e.event_sequence > requested]
                return ConnectResult(subscriber=subscriber, replay=replay)
            return ConnectResult(subscriber=subscriber, resync_required=True)

    async def disconnect(self, subscriber: Subscriber) -> None:
        """Remove a subscriber (idempotent)."""

        async with self._lock:
            subscriber.closed = True
            self._subscribers.discard(subscriber)

    async def close(self) -> None:
        """Close the broker: signal all subscribers to drain and stop."""

        async with self._lock:
            self._closed = True
            for subscriber in self._subscribers:
                subscriber.signal.set()

    async def build_resync_event(self) -> ProgressEvent:
        """Build (but do not persist) a resync control event with a fresh id."""

        async with self._lock:
            self._sequence += 1
            return self._build_event(
                self._sequence,
                ProgressEventType.STREAM_RESYNC_REQUIRED,
                document_id=None,
                job_id=None,
                stage=None,
                percent=None,
                message="The live stream fell behind; refetch the session snapshot.",
                queue_position=None,
                document_status=None,
                job_status=None,
                canonicalisation_method=None,
                canonical_page_count=None,
                canonical_status=None,
            )

    async def stream(self, subscriber: Subscriber) -> AsyncIterator[ProgressEvent]:
        """Yield live events for a subscriber until closed, overflowed, or gone."""

        while True:
            if subscriber.overflow:
                yield await self.build_resync_event()
                return
            if subscriber.closed and subscriber.queue.empty():
                return

            getter: asyncio.Task[ProgressEvent] = asyncio.ensure_future(subscriber.queue.get())
            waiter: asyncio.Task[bool] = asyncio.ensure_future(subscriber.signal.wait())
            try:
                done, _ = await asyncio.wait({getter, waiter}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                # Ensure neither helper task is left pending if this generator is
                # closed (client disconnect) while awaiting: no orphan tasks.
                for task in (getter, waiter):
                    if not task.done():
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task

            if getter in done:
                yield getter.result()
                continue

            if subscriber.overflow:
                yield await self.build_resync_event()
                return
            # Broker closed: drain any buffered events (e.g. session.deleted) first.
            while not subscriber.queue.empty():
                yield subscriber.queue.get_nowait()
            return

"""In-memory session registry.

Holds all runtime sessions for the single application process. Mutations are
guarded by an async lock. Deleted sessions are removed promptly (no unbounded
tombstone storage), and expired/deleting sessions are reported as
``session_not_found`` / ``session_expired`` to external callers.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.identifiers import new_session_id
from backend.app.contracts.jobs import JobStatus
from backend.app.contracts.progress import ProgressEventType
from backend.app.contracts.sessions import SessionStatus
from backend.app.observability.errors import ApiException
from backend.app.processing.queue import JobQueue
from backend.app.progress.broker import EventBroker
from backend.app.progress.models import BrokerClosedError
from backend.app.sessions.models import RuntimeSession
from backend.app.settings.config import Settings
from backend.app.storage.file_store import FileStore


class SessionDeletionReason(StrEnum):
    """Why a session is being torn down (for logging and terminal status)."""

    USER_DELETED = "user_deleted"
    RESET = "reset"
    EXPIRED = "expired"
    SHUTDOWN = "shutdown"


_REASON_STATUS = {
    SessionDeletionReason.USER_DELETED: SessionStatus.DELETED,
    SessionDeletionReason.RESET: SessionStatus.RESET,
    SessionDeletionReason.EXPIRED: SessionStatus.EXPIRED,
    SessionDeletionReason.SHUTDOWN: SessionStatus.DELETED,
}


class SessionRegistry:
    """A process-local, async-safe registry of runtime sessions."""

    def __init__(self, settings: Settings, file_store: FileStore, job_queue: JobQueue) -> None:
        self._settings = settings
        self._file_store = file_store
        self._job_queue = job_queue
        self._sessions: dict[str, RuntimeSession] = {}
        self._lock = asyncio.Lock()

    async def create(self) -> RuntimeSession:
        """Create a new session, its storage, broker, and initial event."""

        session_id = new_session_id()
        root = self._file_store.create_session_storage(session_id)
        broker = EventBroker(
            session_id,
            replay_max=self._settings.sse_replay_max_events,
            subscriber_queue_size=self._settings.sse_subscriber_queue_size,
        )
        now = datetime.now(UTC)
        monotonic = time.monotonic()
        ttl = self._settings.session_ttl_seconds
        session = RuntimeSession(
            session_id=session_id,
            root=root,
            broker=broker,
            ttl_seconds=ttl,
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(seconds=ttl),
            monotonic_deadline=monotonic + ttl,
            status=SessionStatus.CREATED,
        )
        async with self._lock:
            self._sessions[session_id] = session
        await broker.publish(ProgressEventType.SESSION_CREATED)
        return session

    def peek(self, session_id: str) -> RuntimeSession | None:
        """Return a session without touching or raising (internal use only)."""

        return self._sessions.get(session_id)

    async def get(self, session_id: str, *, touch: bool = True) -> RuntimeSession:
        """Return a live session, optionally recording activity.

        Raises ``session_not_found`` for absent/deleting sessions and
        ``session_expired`` for sessions past their deadline but not yet cleaned.
        """

        async with self._lock:
            session = self._sessions.get(session_id)
            monotonic = time.monotonic()
            if session is None or session.deleting:
                raise ApiException(
                    status_code=404,
                    code=ErrorCode.SESSION_NOT_FOUND,
                    message="Session not found.",
                )
            if session.is_expired(monotonic):
                raise ApiException(
                    status_code=404,
                    code=ErrorCode.SESSION_EXPIRED,
                    message="This temporary session has expired and its files were removed.",
                )
            if touch:
                session.touch(monotonic)
            return session

    async def list_expired(self, now_monotonic: float) -> list[RuntimeSession]:
        """Return sessions past their monotonic deadline (not already deleting)."""

        async with self._lock:
            return [
                session
                for session in self._sessions.values()
                if not session.deleting and session.is_expired(now_monotonic)
            ]

    async def active_session_ids(self) -> set[str]:
        async with self._lock:
            return set(self._sessions.keys())

    async def count(self) -> int:
        async with self._lock:
            return len(self._sessions)

    async def delete(self, session_id: str, reason: SessionDeletionReason) -> None:
        """Tear down a session: cancel jobs, notify, close SSE, delete files."""

        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.deleting:
                raise ApiException(
                    status_code=404,
                    code=ErrorCode.SESSION_NOT_FOUND,
                    message="Session not found.",
                )
            session.deleting = True
            session.status = _REASON_STATUS[reason]

        await self._teardown(session)

        async with self._lock:
            self._sessions.pop(session_id, None)

    async def close_all(self, reason: SessionDeletionReason) -> None:
        """Tear down every session (graceful shutdown)."""

        async with self._lock:
            sessions = list(self._sessions.values())
            for session in sessions:
                session.deleting = True
                session.status = _REASON_STATUS[reason]
        for session in sessions:
            await self._teardown(session)
        async with self._lock:
            self._sessions.clear()

    async def _teardown(self, session: RuntimeSession) -> None:
        for job in list(session.jobs.values()):
            if job.is_terminal:
                continue
            if job.status is JobStatus.QUEUED:
                await self._job_queue.cancel(job.job_id)
                job.status = JobStatus.CANCELLED
                job.finished_at = datetime.now(UTC)
            job.request_cancellation()
        await self._await_idle(session)
        with contextlib.suppress(BrokerClosedError):
            await session.broker.publish(ProgressEventType.SESSION_DELETED)
        await session.broker.close()
        self._file_store.remove_session_storage(session.session_id)

    @staticmethod
    async def _await_idle(session: RuntimeSession, *, max_wait: float = 5.0) -> None:
        """Wait (bounded) for any active admission to cooperatively finish."""

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(session.idle_event.wait(), timeout=max_wait)

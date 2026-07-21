"""TTL-based session cleanup.

A single sweep emits a one-time ``session.expiring`` warning for sessions inside
their warning window, and fully tears down sessions past their monotonic
deadline (cancelling jobs, closing SSE, and deleting their storage). Startup and
shutdown sweeps ensure no session directory outlives the process.
"""

from __future__ import annotations

import contextlib
import logging
import time

from backend.app.contracts.progress import ProgressEventType
from backend.app.observability.errors import ApiException
from backend.app.progress.models import BrokerClosedError
from backend.app.sessions.registry import SessionDeletionReason, SessionRegistry
from backend.app.settings.config import Settings
from backend.app.storage.file_store import FileStore

logger = logging.getLogger("veridemand.cleanup")


class CleanupService:
    """Performs expiry warnings, TTL expiry, and startup/shutdown cleanup."""

    def __init__(
        self, registry: SessionRegistry, file_store: FileStore, settings: Settings
    ) -> None:
        self._registry = registry
        self._file_store = file_store
        self._settings = settings

    async def sweep_once(self) -> None:
        """Warn near-expiry sessions and expire those past their deadline."""

        now = time.monotonic()
        warning_seconds = self._settings.session_expiring_warning_seconds
        for session in await self._registry.snapshot():
            if session.deleting:
                continue
            if session.is_expired(now):
                with contextlib.suppress(ApiException):
                    await self._registry.delete(session.session_id, SessionDeletionReason.EXPIRED)
                continue
            if not session.expiring_warned and session.in_warning_window(now, warning_seconds):
                session.expiring_warned = True
                with contextlib.suppress(BrokerClosedError):
                    await session.broker.publish(
                        ProgressEventType.SESSION_EXPIRING,
                        message="This session will expire soon and its files will be removed.",
                    )

    def startup_sweep(self) -> list[str]:
        """Remove any on-disk session directories with no in-memory owner."""

        removed = self._file_store.sweep_abandoned_sessions(set())
        if removed:
            logger.info("Startup cleanup removed %d abandoned session directories.", len(removed))
        return removed

    async def shutdown_cleanup(self) -> None:
        """Tear down all sessions and remove their storage on shutdown."""

        await self._registry.close_all(SessionDeletionReason.SHUTDOWN)
        # Belt-and-braces: remove any residual directories left behind.
        self._file_store.sweep_abandoned_sessions(set())

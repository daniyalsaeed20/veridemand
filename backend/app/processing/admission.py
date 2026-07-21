"""Queue-admission processor.

The Phase 1 admission processor performs **no** extraction, canonicalisation,
rendering, text reading, OCR, or LLM calls. It only confirms runtime ownership
and file integrity, honours cancellation, and marks the document ready for a
future extraction phase.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from backend.app.contracts.documents import DocumentStatus
from backend.app.processing.cancellation import CancellationToken
from backend.app.sessions.models import RuntimeDocument, RuntimeSession
from backend.app.storage.file_store import FileStore

# Granularity of the cooperative test-only admission hold, so cancellation is
# still observed promptly while a job is intentionally held.
_HOLD_TICK_SECONDS = 0.05


class AdmissionError(RuntimeError):
    """Raised when admission fails a runtime-integrity check."""


class AdmissionProcessor(Protocol):
    async def prepare(
        self,
        session: RuntimeSession,
        document: RuntimeDocument,
        cancellation: CancellationToken,
    ) -> None: ...


class Phase1AdmissionProcessor:
    """Non-extractive admission: verify ownership/integrity, then mark ready."""

    def __init__(self, file_store: FileStore, *, test_hold_seconds: float = 0.0) -> None:
        self._file_store = file_store
        self._test_hold_seconds = max(0.0, test_hold_seconds)

    async def prepare(
        self,
        session: RuntimeSession,
        document: RuntimeDocument,
        cancellation: CancellationToken,
    ) -> None:
        cancellation.raise_if_cancelled()
        if session.deleting:
            raise AdmissionError("Session is being deleted.")
        if document.document_id not in session.documents:
            raise AdmissionError("Document no longer belongs to the session.")

        path = self._file_store.original_path(
            session.session_id, document.document_id, document.extension
        )
        if not path.exists():
            raise AdmissionError("Accepted original is missing.")
        if path.stat().st_size != document.size_bytes:
            raise AdmissionError("Accepted original size mismatch.")

        await self._maybe_hold(cancellation)

        cancellation.raise_if_cancelled()
        document.status = DocumentStatus.READY_FOR_EXTRACTION

    async def _maybe_hold(self, cancellation: CancellationToken) -> None:
        """Test-only cooperative delay so E2E can exercise cancellation."""

        remaining = self._test_hold_seconds
        while remaining > 0:
            cancellation.raise_if_cancelled()
            await asyncio.sleep(min(_HOLD_TICK_SECONDS, remaining))
            remaining -= _HOLD_TICK_SECONDS

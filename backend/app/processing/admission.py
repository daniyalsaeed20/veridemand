"""Queue-admission processor.

The Phase 1 admission processor performs **no** extraction, canonicalisation,
rendering, text reading, OCR, or LLM calls. It only confirms runtime ownership
and file integrity, honours cancellation, and marks the document ready for a
future extraction phase.
"""

from __future__ import annotations

from typing import Protocol

from backend.app.contracts.documents import DocumentStatus
from backend.app.processing.cancellation import CancellationToken
from backend.app.sessions.models import RuntimeDocument, RuntimeSession
from backend.app.storage.file_store import FileStore


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

    def __init__(self, file_store: FileStore) -> None:
        self._file_store = file_store

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

        cancellation.raise_if_cancelled()
        document.status = DocumentStatus.READY_FOR_EXTRACTION

"""Canonicalisation processor orchestrating format-specific producers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from backend.app.canonical.errors import CanonicalisationError
from backend.app.canonical.images import canonicalise_image_pdf
from backend.app.canonical.libreoffice import LibreOfficeService
from backend.app.canonical.models import CanonicalisationResult
from backend.app.canonical.pdf import canonicalise_original_pdf
from backend.app.canonical.service import CanonicalisationService
from backend.app.canonical.text import canonicalise_text_pdf
from backend.app.canonical.word import canonicalise_word_pdf
from backend.app.contracts.canonical import CanonicalStatus
from backend.app.contracts.documents import DocumentFormat, PageCountStatus
from backend.app.contracts.errors import ErrorCode
from backend.app.processing.cancellation import CancellationToken, JobCancelledError
from backend.app.processing.models import ProcessingJob
from backend.app.sessions.models import RuntimeDocument, RuntimeSession
from backend.app.settings.config import Settings
from backend.app.storage.file_store import FileStore

_IMAGE_FORMATS = frozenset(
    {
        DocumentFormat.JPEG,
        DocumentFormat.PNG,
        DocumentFormat.TIFF,
        DocumentFormat.BMP,
        DocumentFormat.WEBP,
    }
)

_PROGRESS_STARTED = 6
_PROGRESS_CONVERTED = 11
_PROGRESS_INSPECTED = 13
_PROGRESS_READY = 15


class CanonicalisationProcessor(Protocol):
    async def canonicalise(
        self,
        session: RuntimeSession,
        document: RuntimeDocument,
        job: ProcessingJob,
        cancellation: CancellationToken,
    ) -> CanonicalisationResult: ...


class DefaultCanonicalisationProcessor:
    """Produce and inspect canonical PDFs for every supported input format."""

    def __init__(
        self,
        settings: Settings,
        file_store: FileStore,
        *,
        thread_workers: int = 1,
        test_hold_seconds: float = 0.0,
    ) -> None:
        self._settings = settings
        self._file_store = file_store
        self._service = CanonicalisationService(settings, temp_root=file_store.temp_root)
        self._libreoffice = LibreOfficeService(settings)
        self._semaphore = asyncio.Semaphore(max(1, thread_workers))
        self._test_hold_seconds = max(0.0, test_hold_seconds)

    async def canonicalise(
        self,
        session: RuntimeSession,
        document: RuntimeDocument,
        job: ProcessingJob,
        cancellation: CancellationToken,
    ) -> CanonicalisationResult:
        cancellation.raise_if_cancelled()
        document.canonical_status = CanonicalStatus.CANONICALISING
        document.progress_percent = _PROGRESS_STARTED

        original = self._file_store.original_path(
            session.session_id, document.document_id, document.extension
        )
        if not original.exists() or original.stat().st_size != document.size_bytes:
            raise CanonicalisationError(
                ErrorCode.CANONICALISATION_FAILED,
                "Accepted original is missing or inconsistent.",
            )

        await self._maybe_hold(cancellation)

        async with self._semaphore:
            cancellation.raise_if_cancelled()
            produced = await asyncio.to_thread(
                self._produce,
                session,
                document,
                job,
                original,
                cancellation,
            )

        cancellation.raise_if_cancelled()
        document.progress_percent = _PROGRESS_INSPECTED
        self._apply_result(document, produced)
        document.progress_percent = _PROGRESS_READY
        return produced

    async def _maybe_hold(self, cancellation: CancellationToken) -> None:
        """Test-only cooperative delay so E2E can exercise cancellation."""

        remaining = self._test_hold_seconds
        tick = 0.05
        while remaining > 0:
            cancellation.raise_if_cancelled()
            await asyncio.sleep(min(tick, remaining))
            remaining -= tick

    def _produce(
        self,
        session: RuntimeSession,
        document: RuntimeDocument,
        job: ProcessingJob,
        original: Path,
        cancellation: CancellationToken,
    ) -> CanonicalisationResult:
        cancellation.raise_if_cancelled()
        fmt = document.format
        if fmt is DocumentFormat.PDF:
            result = canonicalise_original_pdf(
                settings=self._settings,
                service=self._service,
                session_id=session.session_id,
                document_id=document.document_id,
                job_id=job.job_id,
                original_path=original,
                warnings=list(document.warnings),
            )
        elif fmt is DocumentFormat.TXT:
            result, encoding = canonicalise_text_pdf(
                settings=self._settings,
                service=self._service,
                session_id=session.session_id,
                document_id=document.document_id,
                job_id=job.job_id,
                original_path=original,
                encoding=document.text_encoding,
                warnings=list(document.warnings),
            )
            document.text_encoding = encoding
        elif fmt in (DocumentFormat.DOC, DocumentFormat.DOCX):
            result = canonicalise_word_pdf(
                settings=self._settings,
                service=self._service,
                libreoffice=self._libreoffice,
                session_id=session.session_id,
                document_id=document.document_id,
                job_id=job.job_id,
                original_path=original,
                fmt=fmt,
                warnings=list(document.warnings),
            )
            document.libreoffice_version = result.libreoffice_version
        elif fmt in _IMAGE_FORMATS:
            result = canonicalise_image_pdf(
                settings=self._settings,
                service=self._service,
                session_id=session.session_id,
                document_id=document.document_id,
                job_id=job.job_id,
                original_path=original,
                warnings=list(document.warnings),
            )
        else:
            raise CanonicalisationError(
                ErrorCode.CANONICALISATION_FAILED,
                "Unsupported format for canonicalisation.",
            )
        document.progress_percent = _PROGRESS_CONVERTED
        cancellation.raise_if_cancelled()
        return result

    @staticmethod
    def _apply_result(document: RuntimeDocument, result: CanonicalisationResult) -> None:
        document.canonical_view_available = True
        document.canonical_size_bytes = result.size_bytes
        document.canonical_sha256 = result.sha256
        document.canonical_page_count = len(result.pages)
        document.canonicalisation_method = result.method
        document.canonical_pages = result.pages
        document.canonical_warning_codes = list(result.warnings)
        document.canonical_status = CanonicalStatus.READY
        document.canonical_created_at = datetime.now(UTC)
        document.page_count = len(result.pages)
        document.page_count_status = PageCountStatus.KNOWN
        if result.libreoffice_version:
            document.libreoffice_version = result.libreoffice_version


__all__ = [
    "_PROGRESS_CONVERTED",
    "_PROGRESS_INSPECTED",
    "_PROGRESS_READY",
    "_PROGRESS_STARTED",
    "CanonicalisationProcessor",
    "DefaultCanonicalisationProcessor",
    "JobCancelledError",
]

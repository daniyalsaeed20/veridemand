"""Internal, mutable runtime session and document models.

These objects are never returned directly through the API. Public read models are
built by ``sessions.service`` from these mutable structures. Expiration
correctness uses a monotonic deadline; wall-clock UTC timestamps are only for
display in API responses.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.app.contracts.documents import (
    DocumentFormat,
    DocumentStatus,
    DocumentStatusCounts,
    DocumentSummary,
    PageCountStatus,
)
from backend.app.contracts.sessions import SessionStatus
from backend.app.processing.models import ProcessingJob
from backend.app.progress.broker import EventBroker

# Progress is always 5% for an accepted document in Phase 1: no extraction.
_DOCUMENT_PROGRESS_PERCENT = 5


@dataclass
class RuntimeDocument:
    """A validated, accepted document held in a runtime session."""

    document_id: str
    display_filename: str
    extension: str
    format: DocumentFormat
    media_type: str
    size_bytes: int
    sha256: str
    page_count: int | None
    page_count_status: PageCountStatus
    status: DocumentStatus = DocumentStatus.UPLOADED
    warnings: list[str] = field(default_factory=list)
    active_job_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_summary(self, queue_position: int | None = None) -> DocumentSummary:
        return DocumentSummary(
            document_id=self.document_id,
            display_filename=self.display_filename,
            extension=self.extension,
            format=self.format,
            media_type=self.media_type,
            size_bytes=self.size_bytes,
            sha256=self.sha256,
            page_count=self.page_count,
            page_count_status=self.page_count_status,
            status=self.status,
            progress_percent=_DOCUMENT_PROGRESS_PERCENT,
            result_available=False,
            extraction_performed=False,
            warning_count=len(self.warnings),
            queue_position=queue_position if self.status is DocumentStatus.QUEUED else None,
            active_job_id=self.active_job_id,
            created_at=self.created_at,
        )


@dataclass
class RuntimeSession:
    """A temporary, runtime-only session owning documents, jobs and storage."""

    session_id: str
    root: Path
    broker: EventBroker
    ttl_seconds: int
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    monotonic_deadline: float
    status: SessionStatus = SessionStatus.CREATED
    documents: dict[str, RuntimeDocument] = field(default_factory=dict)
    jobs: dict[str, ProcessingJob] = field(default_factory=dict)
    accepted_bytes: int = 0
    known_pages: int = 0
    expiring_warned: bool = False
    deleting: bool = False
    active_admissions: int = 0
    upload_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    state_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    idle_event: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        # No admission is running initially, so the session starts idle.
        self.idle_event.set()

    def begin_admission(self) -> None:
        """Mark that an admission worker started reading this session's metadata."""

        self.active_admissions += 1
        self.idle_event.clear()

    def end_admission(self) -> None:
        """Mark that an admission worker finished; signal idle when none remain."""

        self.active_admissions = max(0, self.active_admissions - 1)
        if self.active_admissions == 0:
            self.idle_event.set()

    def touch(self, now_monotonic: float) -> None:
        """Record activity: refresh last-activity and extend the TTL deadline."""

        now = datetime.now(UTC)
        self.last_activity_at = now
        self.expires_at = now + timedelta(seconds=self.ttl_seconds)
        self.monotonic_deadline = now_monotonic + self.ttl_seconds
        self.expiring_warned = False

    def seconds_remaining(self, now_monotonic: float) -> int:
        remaining = self.monotonic_deadline - now_monotonic
        return max(0, int(remaining))

    def is_expired(self, now_monotonic: float) -> bool:
        return now_monotonic >= self.monotonic_deadline

    def in_warning_window(self, now_monotonic: float, warning_seconds: int) -> bool:
        return self.seconds_remaining(now_monotonic) <= warning_seconds

    def unknown_page_documents(self) -> int:
        return sum(
            1
            for doc in self.documents.values()
            if doc.page_count_status is PageCountStatus.PENDING_CANONICALISATION
        )

    def status_counts(self) -> DocumentStatusCounts:
        counts = DocumentStatusCounts()
        for doc in self.documents.values():
            match doc.status:
                case DocumentStatus.UPLOADED:
                    counts.uploaded += 1
                case DocumentStatus.QUEUED:
                    counts.queued += 1
                case DocumentStatus.PREPARING:
                    counts.preparing += 1
                case DocumentStatus.READY_FOR_EXTRACTION:
                    counts.ready_for_extraction += 1
                case DocumentStatus.CANCELLED:
                    counts.cancelled += 1
                case DocumentStatus.FAILED:
                    counts.failed += 1
        return counts

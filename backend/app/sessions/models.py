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

from backend.app.contracts.canonical import (
    CanonicalisationMethod,
    CanonicalPageMetadata,
    CanonicalStatus,
)
from backend.app.contracts.documents import (
    MAX_PHASE4_PROGRESS_PERCENT,
    DocumentFormat,
    DocumentStatus,
    DocumentStatusCounts,
    DocumentSummary,
    PageCountStatus,
)
from backend.app.contracts.native import DocumentSourcePolicy
from backend.app.contracts.sessions import SessionStatus
from backend.app.processing.models import ProcessingJob
from backend.app.progress.broker import EventBroker

_DEFAULT_PROGRESS_PERCENT = 5


def _document_progress_percent(document: RuntimeDocument) -> int:
    """Map status to progress floors; never let a stale native % hide visual stage."""

    stored = min(document.progress_percent, MAX_PHASE4_PROGRESS_PERCENT)
    match document.status:
        case DocumentStatus.UPLOADED | DocumentStatus.QUEUED:
            return 5 if stored == _DEFAULT_PROGRESS_PERCENT else max(5, stored)
        case DocumentStatus.CANONICALISING:
            return max(6, stored) if stored != _DEFAULT_PROGRESS_PERCENT else 6
        case DocumentStatus.READY_FOR_EXTRACTION:
            floor = 15 if document.canonical_view_available else 5
            return max(floor, stored) if stored != _DEFAULT_PROGRESS_PERCENT else floor
        case DocumentStatus.INSPECTING_NATIVE:
            return max(16, stored) if stored != _DEFAULT_PROGRESS_PERCENT else 16
        case DocumentStatus.EXTRACTING_NATIVE:
            return max(20, stored) if stored != _DEFAULT_PROGRESS_PERCENT else 20
        case DocumentStatus.NATIVE_TRUST_COMPLETE:
            return max(35, stored) if stored != _DEFAULT_PROGRESS_PERCENT else 35
        case DocumentStatus.VISUAL_PENDING:
            return max(36, stored) if stored != _DEFAULT_PROGRESS_PERCENT else 36
        case DocumentStatus.VISUAL_PROCESSING:
            return max(36, min(stored if stored != _DEFAULT_PROGRESS_PERCENT else 36, 64))
        case DocumentStatus.VISUAL_PROCESSING_COMPLETE | DocumentStatus.VISUAL_PROCESSING_PARTIAL:
            return 65
        case DocumentStatus.VISUAL_PROCESSING_FAILED:
            # Terminal visual failure always reports the Phase 4 cap so the UI
            # cannot remain stuck on a native-band percentage (e.g. 32%).
            return MAX_PHASE4_PROGRESS_PERCENT
        case DocumentStatus.FAILED | DocumentStatus.CANCELLED:
            return min(stored, MAX_PHASE4_PROGRESS_PERCENT)
        case _:
            return (
                5
                if stored == _DEFAULT_PROGRESS_PERCENT
                else min(stored, MAX_PHASE4_PROGRESS_PERCENT)
            )


def _canonical_urls(
    document: RuntimeDocument,
    session_id: str,
    *,
    api_prefix: str,
) -> tuple[str | None, str | None, str | None, str | None]:
    if not document.canonical_view_available:
        return None, None, None, None
    base = f"{api_prefix}/sessions/{session_id}/documents/{document.document_id}"
    native_url = f"{base}/native/summary" if document.native_extraction_performed else None
    visual_url = f"{base}/visual/summary" if document.visual_processing_performed else None
    return f"{base}/canonical", f"{base}/canonical/metadata", native_url, visual_url


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
    text_encoding: str | None = None
    canonical_status: CanonicalStatus = CanonicalStatus.PENDING
    canonicalisation_method: CanonicalisationMethod | None = None
    canonical_view_available: bool = False
    canonical_size_bytes: int | None = None
    canonical_sha256: str | None = None
    canonical_page_count: int | None = None
    canonical_created_at: datetime | None = None
    canonical_failure_code: str | None = None
    canonical_warning_codes: list[str] = field(default_factory=list)
    canonical_pages: list[CanonicalPageMetadata] = field(default_factory=list)
    progress_percent: int = _DEFAULT_PROGRESS_PERCENT
    libreoffice_version: str | None = None
    native_extraction_performed: bool = False
    native_result_available: bool = False
    visual_processing_required: bool = False
    visual_processing_performed: bool = False
    visual_result_available: bool = False
    pages_completed: int | None = None
    pages_total: int | None = None
    document_source_policy: DocumentSourcePolicy | None = None
    user_status_message: str | None = None
    failure_stage: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    failure_page_number: int | None = None
    major_phase: str | None = None
    major_phase_percent: float | None = None
    page_percent: float | None = None
    active_page_number: int | None = None
    current_operation: str | None = None
    operation_status: str | None = None
    progress_kind: str | None = None
    elapsed_seconds: float | None = None
    document_elapsed_seconds: float | None = None
    page_elapsed_seconds: float | None = None
    operation_elapsed_seconds: float | None = None
    deadline_remaining_seconds: float | None = None
    worker_generation: int | None = None
    worker_restart_count: int | None = None
    attempt_number: int | None = None
    max_attempts: int | None = None
    stage_timeline: list[dict[str, object]] = field(default_factory=list)

    def to_summary(
        self,
        queue_position: int | None = None,
        *,
        session_id: str | None = None,
        api_prefix: str | None = None,
    ) -> DocumentSummary:
        canonical_view_url: str | None = None
        canonical_metadata_url: str | None = None
        native_summary_url: str | None = None
        visual_summary_url: str | None = None
        if session_id is not None and api_prefix is not None:
            (
                canonical_view_url,
                canonical_metadata_url,
                native_summary_url,
                visual_summary_url,
            ) = _canonical_urls(self, session_id, api_prefix=api_prefix)
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
            progress_percent=_document_progress_percent(self),
            result_available=False,
            extraction_performed=False,
            native_extraction_performed=self.native_extraction_performed,
            native_result_available=self.native_result_available,
            visual_processing_required=self.visual_processing_required,
            visual_processing_performed=self.visual_processing_performed,
            visual_result_available=self.visual_result_available,
            document_source_policy=self.document_source_policy,
            user_status_message=self.user_status_message,
            failure_stage=self.failure_stage,
            failure_code=self.failure_code,
            failure_message=self.failure_message,
            failure_page_number=self.failure_page_number,
            warning_count=len(self.warnings),
            queue_position=queue_position if self.status is DocumentStatus.QUEUED else None,
            active_job_id=self.active_job_id,
            created_at=self.created_at,
            canonical_status=(
                None if self.canonical_status is CanonicalStatus.PENDING else self.canonical_status
            ),
            canonicalisation_method=self.canonicalisation_method,
            canonical_view_available=self.canonical_view_available,
            canonical_view_url=canonical_view_url,
            canonical_metadata_url=canonical_metadata_url,
            native_summary_url=native_summary_url,
            visual_summary_url=visual_summary_url,
            pages_completed=self.pages_completed,
            pages_total=self.pages_total,
            major_phase=self.major_phase,
            major_phase_percent=self.major_phase_percent,
            page_percent=self.page_percent,
            active_page_number=self.active_page_number,
            current_operation=self.current_operation,
            operation_status=self.operation_status,
            progress_kind=self.progress_kind,
            elapsed_seconds=self.elapsed_seconds,
            document_elapsed_seconds=self.document_elapsed_seconds,
            page_elapsed_seconds=self.page_elapsed_seconds,
            operation_elapsed_seconds=self.operation_elapsed_seconds,
            deadline_remaining_seconds=self.deadline_remaining_seconds,
            worker_generation=self.worker_generation,
            worker_restart_count=self.worker_restart_count,
            attempt_number=self.attempt_number,
            max_attempts=self.max_attempts,
            stage_timeline=list(self.stage_timeline[-32:]) or None,
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
        self.idle_event.set()

    def begin_admission(self) -> None:
        self.active_admissions += 1
        self.idle_event.clear()

    def end_admission(self) -> None:
        self.active_admissions = max(0, self.active_admissions - 1)
        if self.active_admissions == 0:
            self.idle_event.set()

    def touch(self, now_monotonic: float) -> None:
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
                case DocumentStatus.CANONICALISING:
                    counts.canonicalising += 1
                case DocumentStatus.READY_FOR_EXTRACTION:
                    counts.ready_for_extraction += 1
                case DocumentStatus.INSPECTING_NATIVE:
                    counts.inspecting_native += 1
                case DocumentStatus.EXTRACTING_NATIVE:
                    counts.extracting_native += 1
                case DocumentStatus.NATIVE_TRUST_COMPLETE:
                    counts.native_trust_complete += 1
                case DocumentStatus.VISUAL_PENDING:
                    counts.visual_pending += 1
                case DocumentStatus.VISUAL_PROCESSING:
                    counts.visual_processing += 1
                case DocumentStatus.VISUAL_PROCESSING_COMPLETE:
                    counts.visual_processing_complete += 1
                case DocumentStatus.VISUAL_PROCESSING_PARTIAL:
                    counts.visual_processing_partial += 1
                case DocumentStatus.VISUAL_PROCESSING_FAILED:
                    counts.visual_processing_failed += 1
                case DocumentStatus.CANCELLED:
                    counts.cancelled += 1
                case DocumentStatus.FAILED:
                    counts.failed += 1
        return counts

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
    # Phase 4.5 live progress / route breakdown.
    progress_version: int | None = None
    current_route: str | None = None
    estimate_status: str | None = None
    estimate_confidence: str | None = None
    estimate_sample_count: int | None = None
    estimated_document_remaining_seconds: float | None = None
    estimated_queue_remaining_seconds: float | None = None
    estimated_completion_at: datetime | None = None
    estimated_current_operation_seconds: float | None = None
    estimated_current_page_seconds: float | None = None
    average_page_seconds: float | None = None
    average_full_ocr_page_seconds: float | None = None
    pages_per_minute: float | None = None
    document_pages_total: int | None = None
    document_page_number: int | None = None
    selected_page_index: int | None = None
    selected_pages_total: int | None = None
    visual_page_index: int | None = None
    visual_pages_total: int | None = None
    route_page_index: int | None = None
    route_pages_total: int | None = None
    operation_id: str | None = None
    native_pages_retained: int | None = None
    native_pages_selected: int | None = None
    native_pages_completed: int | None = None
    embedded_verification_pages_selected: int | None = None
    embedded_verification_pages_completed: int | None = None
    embedded_ocr_pages_verified: int | None = None
    targeted_repair_pages_selected: int | None = None
    targeted_repair_pages_completed: int | None = None
    full_ocr_pages_selected: int | None = None
    full_ocr_pages_completed: int | None = None
    full_ocr_pages_remaining: int | None = None
    visual_no_text_pages: int | None = None
    failed_pages: int | None = None
    pages_terminal_total: int | None = None
    pages_remaining: int | None = None
    fair_scheduling_enabled: bool | None = None
    scheduler_document_state: str | None = None
    scheduler_priority_class: str | None = None
    scheduler_effective_priority: int | None = None
    scheduler_queue_position: int | None = None
    scheduler_turn_number: int | None = None
    scheduler_quantum: int | None = None
    scheduler_quantum_completed: int | None = None
    scheduler_remaining_work_units: int | None = None
    scheduler_waiting_seconds: float | None = None
    scheduler_turns_skipped: int | None = None
    estimated_next_turn_seconds: float | None = None
    estimated_waiting_seconds: float | None = None
    document_started_at: datetime | None = None
    phase_started_at: datetime | None = None
    page_started_at: datetime | None = None
    operation_started_at: datetime | None = None
    phase_elapsed_seconds: float | None = None
    server_timestamp: datetime | None = None
    batch_elapsed_seconds: float | None = None
    attempt_elapsed_seconds: float | None = None
    batch_started_at_timestamp: datetime | None = None
    document_started_at_timestamp: datetime | None = None
    document_deadline_remaining_seconds: float | None = None
    page_deadline_remaining_seconds: float | None = None
    operation_deadline_remaining_seconds: float | None = None
    attempt_deadline_remaining_seconds: float | None = None
    slow_warning_status: str | None = None
    slow_warning_operation_id: str | None = None
    slow_warning_started_at: datetime | None = None
    slow_warning_threshold_seconds: float | None = None
    slow_warning_reason: str | None = None
    estimated_batch_remaining_seconds: float | None = None
    estimated_batch_completion_at: datetime | None = None
    estimated_document_completion_at: datetime | None = None

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
            progress_version=self.progress_version,
            current_route=self.current_route,
            estimate_status=self.estimate_status,
            estimate_confidence=self.estimate_confidence,
            estimate_sample_count=self.estimate_sample_count,
            estimated_document_remaining_seconds=self.estimated_document_remaining_seconds,
            estimated_queue_remaining_seconds=self.estimated_queue_remaining_seconds,
            estimated_completion_at=self.estimated_completion_at,
            estimated_current_operation_seconds=self.estimated_current_operation_seconds,
            estimated_current_page_seconds=self.estimated_current_page_seconds,
            average_page_seconds=self.average_page_seconds,
            average_full_ocr_page_seconds=self.average_full_ocr_page_seconds,
            pages_per_minute=self.pages_per_minute,
            document_pages_total=self.document_pages_total,
            document_page_number=self.document_page_number,
            selected_page_index=self.selected_page_index,
            selected_pages_total=self.selected_pages_total,
            visual_page_index=self.visual_page_index,
            visual_pages_total=self.visual_pages_total,
            route_page_index=self.route_page_index,
            route_pages_total=self.route_pages_total,
            operation_id=self.operation_id,
            native_pages_retained=self.native_pages_retained,
            native_pages_selected=self.native_pages_selected,
            native_pages_completed=self.native_pages_completed,
            embedded_verification_pages_selected=self.embedded_verification_pages_selected,
            embedded_verification_pages_completed=self.embedded_verification_pages_completed,
            embedded_ocr_pages_verified=self.embedded_ocr_pages_verified,
            targeted_repair_pages_selected=self.targeted_repair_pages_selected,
            targeted_repair_pages_completed=self.targeted_repair_pages_completed,
            full_ocr_pages_selected=self.full_ocr_pages_selected,
            full_ocr_pages_completed=self.full_ocr_pages_completed,
            full_ocr_pages_remaining=self.full_ocr_pages_remaining,
            visual_no_text_pages=self.visual_no_text_pages,
            failed_pages=self.failed_pages,
            pages_terminal_total=self.pages_terminal_total,
            pages_remaining=self.pages_remaining,
            fair_scheduling_enabled=self.fair_scheduling_enabled,
            scheduler_document_state=self.scheduler_document_state,
            scheduler_priority_class=self.scheduler_priority_class,
            scheduler_effective_priority=self.scheduler_effective_priority,
            scheduler_queue_position=self.scheduler_queue_position,
            scheduler_turn_number=self.scheduler_turn_number,
            scheduler_quantum=self.scheduler_quantum,
            scheduler_quantum_completed=self.scheduler_quantum_completed,
            scheduler_remaining_work_units=self.scheduler_remaining_work_units,
            scheduler_waiting_seconds=self.scheduler_waiting_seconds,
            scheduler_turns_skipped=self.scheduler_turns_skipped,
            estimated_next_turn_seconds=self.estimated_next_turn_seconds,
            estimated_waiting_seconds=self.estimated_waiting_seconds,
            document_started_at=self.document_started_at,
            phase_started_at=self.phase_started_at,
            page_started_at=self.page_started_at,
            operation_started_at=self.operation_started_at,
            phase_elapsed_seconds=self.phase_elapsed_seconds,
            server_timestamp=self.server_timestamp,
            batch_elapsed_seconds=self.batch_elapsed_seconds,
            attempt_elapsed_seconds=self.attempt_elapsed_seconds,
            batch_started_at_timestamp=self.batch_started_at_timestamp,
            document_started_at_timestamp=self.document_started_at_timestamp,
            document_deadline_remaining_seconds=self.document_deadline_remaining_seconds,
            page_deadline_remaining_seconds=self.page_deadline_remaining_seconds,
            operation_deadline_remaining_seconds=self.operation_deadline_remaining_seconds,
            attempt_deadline_remaining_seconds=self.attempt_deadline_remaining_seconds,
            slow_warning_status=self.slow_warning_status,
            slow_warning_operation_id=self.slow_warning_operation_id,
            slow_warning_started_at=self.slow_warning_started_at,
            slow_warning_threshold_seconds=self.slow_warning_threshold_seconds,
            slow_warning_reason=self.slow_warning_reason,
            estimated_batch_remaining_seconds=self.estimated_batch_remaining_seconds,
            estimated_batch_completion_at=self.estimated_batch_completion_at,
            estimated_document_completion_at=self.estimated_document_completion_at,
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

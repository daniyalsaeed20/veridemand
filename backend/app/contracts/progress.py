"""Progress event contract for the Server-Sent Events stream.

``ProgressEvent`` is the single, strict shape delivered over SSE and embedded in
the session snapshot (so it is exported to OpenAPI and generated as a reusable
frontend Zod schema). Extraction-stage event types are *reserved* here but never
emitted in Phase 1.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from backend.app.contracts.base import ApiModel
from backend.app.contracts.documents import DocumentStatus
from backend.app.contracts.identifiers import DocumentId, EventId, JobId, SessionId
from backend.app.contracts.jobs import JobStatus


class ProgressEventType(StrEnum):
    """All event types the SSE stream may carry.

    Extraction-stage types are reserved for later phases and are never emitted in
    Phase 1.
    """

    SESSION_CREATED = "session.created"
    SESSION_SNAPSHOT = "session.snapshot"
    SESSION_EXPIRING = "session.expiring"
    SESSION_DELETED = "session.deleted"

    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_REJECTED = "document.rejected"
    DOCUMENT_QUEUED = "document.queued"
    DOCUMENT_STARTED = "document.started"
    DOCUMENT_STAGE_CHANGED = "document.stage_changed"
    DOCUMENT_CANONICALISATION_STARTED = "document.canonicalisation_started"
    DOCUMENT_CANONICALISATION_PROGRESS = "document.canonicalisation_progress"
    DOCUMENT_CANONICALISATION_COMPLETED = "document.canonicalisation_completed"
    DOCUMENT_CANONICALISATION_FAILED = "document.canonicalisation_failed"
    DOCUMENT_CANONICALISATION_CANCELLED = "document.canonicalisation_cancelled"
    DOCUMENT_CANONICAL_READY = "document.canonical_ready"
    DOCUMENT_READY_FOR_EXTRACTION = "document.ready_for_extraction"
    DOCUMENT_NATIVE_INSPECTION_STARTED = "document.native_inspection_started"
    DOCUMENT_NATIVE_PAGE_STARTED = "document.native_page_started"
    DOCUMENT_NATIVE_PAGE_ACCEPTED = "document.native_page_accepted"
    DOCUMENT_NATIVE_PAGE_REJECTED = "document.native_page_rejected"
    DOCUMENT_NATIVE_PAGE_ABSENT = "document.native_page_absent"
    DOCUMENT_NATIVE_PAGE_ERROR = "document.native_page_error"
    DOCUMENT_NATIVE_DOCUMENT_ESCALATED = "document.native_document_escalated"
    DOCUMENT_NATIVE_EXTRACTION_COMPLETED = "document.native_extraction_completed"
    DOCUMENT_NATIVE_EXTRACTION_FAILED = "document.native_extraction_failed"
    DOCUMENT_VISUAL_PROCESSING_STARTED = "document.visual_processing_started"
    DOCUMENT_VISUAL_PAGES_SELECTED = "document.visual_pages_selected"
    DOCUMENT_NATIVE_VISIBILITY_STARTED = "document.native_visibility_started"
    DOCUMENT_NATIVE_VISIBILITY_SUPPORTED = "document.native_visibility_supported"
    DOCUMENT_NATIVE_VISIBILITY_REJECTED = "document.native_visibility_rejected"
    DOCUMENT_VISUAL_PAGE_STARTED = "document.visual_page_started"
    DOCUMENT_VISUAL_PAGE_RENDERED = "document.visual_page_rendered"
    DOCUMENT_VISUAL_PAGE_OCR_STARTED = "document.visual_page_ocr_started"
    DOCUMENT_VISUAL_PAGE_OCR_COMPLETED = "document.visual_page_ocr_completed"
    DOCUMENT_VISUAL_PAGE_NO_TEXT = "document.visual_page_no_text"
    DOCUMENT_VISUAL_PAGE_FAILED = "document.visual_page_failed"
    DOCUMENT_VISUAL_GROUPING_COMPLETED = "document.visual_grouping_completed"
    DOCUMENT_VISUAL_PROCESSING_COMPLETED = "document.visual_processing_completed"
    DOCUMENT_VISUAL_PROCESSING_PARTIAL = "document.visual_processing_partial"
    DOCUMENT_VISUAL_PROCESSING_FAILED = "document.visual_processing_failed"
    DOCUMENT_REMOVED = "document.removed"
    DOCUMENT_WARNING = "document.warning"
    DOCUMENT_FAILED = "document.failed"
    DOCUMENT_CANCELLED = "document.cancelled"

    JOB_QUEUED = "job.queued"
    JOB_STARTED = "job.started"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    JOB_CANCELLED = "job.cancelled"

    STREAM_RESYNC_REQUIRED = "stream.resync_required"
    HEARTBEAT = "heartbeat"

    # Reserved for later phases.
    DOCUMENT_PAGE_STARTED = "document.page_started"
    DOCUMENT_PAGE_COMPLETED = "document.page_completed"
    DOCUMENT_COMPLETED = "document.completed"


class ProgressEvent(ApiModel):
    """A single, strictly-validated progress event."""

    event_id: EventId = Field(description="Per-session stable event identifier.")
    event_sequence: int = Field(ge=1, description="Monotonic per-session sequence number.")
    event: ProgressEventType = Field(description="Event type.")
    session_id: SessionId = Field(description="Owning session identifier.")
    document_id: DocumentId | None = Field(default=None, description="Related document, if any.")
    job_id: JobId | None = Field(default=None, description="Related job, if any.")
    timestamp: datetime = Field(description="Timezone-aware UTC time of the event.")
    stage: str | None = Field(default=None, description="Optional stage label.")
    percent: int | None = Field(
        default=None, ge=0, le=100, description="Optional progress percent."
    )
    page_number: int | None = Field(default=None, ge=1, description="Reserved; unused in Phase 1.")
    pages_completed: int | None = Field(
        default=None, ge=0, description="Reserved; unused in Phase 1."
    )
    pages_total: int | None = Field(default=None, ge=0, description="Reserved; unused in Phase 1.")
    message: str | None = Field(default=None, description="Optional safe, non-sensitive message.")
    queue_position: int | None = Field(
        default=None, ge=1, description="Queue position, if relevant."
    )
    document_status: DocumentStatus | None = Field(
        default=None, description="Document status at the time of the event, if relevant."
    )
    job_status: JobStatus | None = Field(
        default=None, description="Job status at the time of the event, if relevant."
    )
    canonicalisation_method: str | None = Field(
        default=None, description="Canonicalisation method when relevant."
    )
    canonical_page_count: int | None = Field(
        default=None, ge=0, description="Canonical page count when known."
    )
    canonical_status: str | None = Field(
        default=None, description="Canonical status when relevant."
    )
    decision: str | None = Field(default=None, description="Native page decision when relevant.")
    source_mode: str | None = Field(default=None, description="Page source mode when relevant.")
    native_trust_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Native trust score when relevant."
    )
    reason_codes: list[str] | None = Field(
        default=None, description="Safe native reason codes when relevant."
    )
    overall_percent: float | None = Field(
        default=None, ge=0.0, le=65.0, description="Document overall progress (Phase 4 cap 65)."
    )
    major_phase: str | None = Field(default=None, description="Major phase label.")
    major_phase_percent: float | None = Field(
        default=None, ge=0.0, le=100.0, description="Major-phase progress 0-100."
    )
    page_percent: float | None = Field(
        default=None, ge=0.0, le=100.0, description="Active page progress 0-100."
    )
    operation: str | None = Field(default=None, description="Stable operation identifier.")
    operation_status: str | None = Field(default=None, description="Operation status.")
    progress_kind: str | None = Field(
        default=None, description="determinate|indeterminate|heartbeat."
    )
    elapsed_seconds: float | None = Field(
        default=None, ge=0.0, description="Document-level elapsed (alias)."
    )
    document_elapsed_seconds: float | None = Field(default=None, ge=0.0)
    page_elapsed_seconds: float | None = Field(default=None, ge=0.0)
    operation_elapsed_seconds: float | None = Field(default=None, ge=0.0)
    stage_elapsed_seconds: float | None = Field(
        default=None, ge=0.0, description="Alias of operation_elapsed_seconds."
    )
    deadline_remaining_seconds: float | None = Field(default=None, ge=0.0)
    worker_pid: int | None = Field(default=None, ge=0)
    worker_generation: int | None = Field(default=None, ge=0)
    worker_restart_count: int | None = Field(default=None, ge=0)
    attempt_number: int | None = Field(default=None, ge=1)
    max_attempts: int | None = Field(default=None, ge=1)
    reason_code: str | None = Field(default=None, description="Safe reason/error code.")

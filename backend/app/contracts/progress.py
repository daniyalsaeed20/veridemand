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
    DOCUMENT_READY_FOR_EXTRACTION = "document.ready_for_extraction"
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

    # Reserved for later phases; never emitted in Phase 1.
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

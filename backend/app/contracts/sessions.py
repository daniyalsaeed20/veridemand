"""Session domain contracts and the public session snapshot.

The snapshot is the single canonical read model returned by session creation,
retrieval, upload and process responses. It never exposes local filesystem
paths, credentials, or internal process configuration.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Final

from pydantic import Field

from backend.app.contracts.base import ApiModel
from backend.app.contracts.documents import DocumentStatusCounts, DocumentSummary
from backend.app.contracts.identifiers import DocumentId, JobId, SessionId
from backend.app.contracts.jobs import JobSummary
from backend.app.contracts.progress import ProgressEvent

RUNTIME_WARNING: Final = (
    "This is a temporary, runtime-only session. Uploaded files are held in server "
    "memory and temporary storage only, are never persisted to a database, and are "
    "permanently removed on reset, expiry, browser refresh, or server shutdown. No "
    "text extraction is performed in this phase."
)


class SessionStatus(StrEnum):
    """Lifecycle state of a runtime session.

    ``ready`` means all currently queued admission jobs finished and files are
    ready for a *future* extraction phase; it does not mean extraction occurred.
    """

    CREATED = "created"
    ACCEPTING_UPLOADS = "accepting_uploads"
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    RESET = "reset"
    EXPIRED = "expired"
    FAILED = "failed"
    DELETED = "deleted"


class SessionLimits(ApiModel):
    """Public, non-sensitive session limits surfaced to the frontend."""

    max_files_per_session: int = Field(gt=0)
    max_pages_per_session: int = Field(gt=0)
    max_single_file_bytes: int = Field(gt=0)
    max_session_bytes: int = Field(gt=0)
    max_filename_length: int = Field(gt=0)
    supported_extensions: list[str] = Field(description="Allowed file extensions (with dot).")


class QueueInfo(ApiModel):
    """Snapshot of the session's queue state."""

    pending: int = Field(default=0, ge=0, description="Queued admission jobs waiting.")
    running: int = Field(default=0, ge=0, description="Admission jobs currently running.")
    active_document_id: DocumentId | None = Field(
        default=None, description="Document currently being admitted, if any."
    )
    active_job_id: JobId | None = Field(default=None, description="Active admission job, if any.")


class SessionSnapshot(ApiModel):
    """Canonical public read model of a runtime session."""

    session_id: SessionId = Field(description="Opaque session identifier.")
    status: SessionStatus = Field(description="Current session status.")
    created_at: datetime = Field(description="Timezone-aware UTC creation time.")
    last_activity_at: datetime = Field(description="Timezone-aware UTC time of last activity.")
    expires_at: datetime = Field(description="Timezone-aware UTC expiry deadline.")
    expiring: bool = Field(
        default=False, description="Whether the session is in its warning window."
    )
    seconds_remaining: int = Field(ge=0, description="Whole seconds until expiry (never negative).")
    limits: SessionLimits = Field(description="Session limits.")
    runtime_warning: str = Field(description="Constant runtime-only warning message.")
    counts: DocumentStatusCounts = Field(description="Document counts by status.")
    accepted_bytes: int = Field(ge=0, description="Total accepted bytes in the session.")
    known_pages: int = Field(ge=0, description="Total known page count across documents.")
    unknown_page_documents: int = Field(
        ge=0, description="Documents whose page count is pending canonicalisation."
    )
    queue: QueueInfo = Field(description="Queue state.")
    documents: list[DocumentSummary] = Field(description="Documents in acceptance order.")
    jobs: list[JobSummary] = Field(description="Jobs in creation order.")
    recent_events: list[ProgressEvent] = Field(description="Bounded recent progress events.")

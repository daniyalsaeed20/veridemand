"""Processing job contracts.

A *completed* Phase 1 job means queue admission finished and the document is
ready for a future extraction phase. It never means extraction occurred.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from backend.app.contracts.base import ApiModel
from backend.app.contracts.identifiers import DocumentId, JobId, SessionId


class JobStatus(StrEnum):
    """Lifecycle state of a queue-admission job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class JobSummary(ApiModel):
    """Public summary of a queue-admission job."""

    job_id: JobId = Field(description="Opaque job identifier.")
    session_id: SessionId = Field(description="Owning session identifier.")
    document_id: DocumentId = Field(description="Target document identifier.")
    status: JobStatus = Field(description="Current job status.")
    queue_position: int | None = Field(
        default=None, ge=1, description="Dynamic 1-based position while queued, else null."
    )
    created_at: datetime = Field(description="Timezone-aware UTC creation time.")
    started_at: datetime | None = Field(default=None, description="When admission began.")
    finished_at: datetime | None = Field(
        default=None, description="When the job reached a terminal state."
    )
    cancellation_requested: bool = Field(
        default=False, description="Whether cooperative cancellation was requested."
    )
    failure_code: str | None = Field(default=None, description="Safe failure code, if failed.")
    failure_message: str | None = Field(
        default=None, description="Safe failure message, if failed."
    )
    attempt: int = Field(
        default=1, ge=1, le=1, description="Attempt number; fixed at 1 in Phase 1."
    )


class JobListResponse(ApiModel):
    """Response body for listing a session's jobs."""

    jobs: list[JobSummary] = Field(description="Jobs in creation order.")

"""Internal, mutable processing-job model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from backend.app.contracts.jobs import JobStatus, JobSummary
from backend.app.processing.cancellation import CancellationToken

_TERMINAL_STATUSES = frozenset({JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED})


@dataclass
class ProcessingJob:
    """A single queue-admission job (Phase 1 performs no extraction)."""

    job_id: str
    session_id: str
    document_id: str
    status: JobStatus = JobStatus.QUEUED
    queue_position: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancellation_requested: bool = False
    failure_code: str | None = None
    failure_message: str | None = None
    attempt: int = 1
    cancellation: CancellationToken = field(default_factory=CancellationToken)

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES

    def request_cancellation(self) -> None:
        self.cancellation_requested = True
        self.cancellation.cancel()

    def to_summary(self) -> JobSummary:
        return JobSummary(
            job_id=self.job_id,
            session_id=self.session_id,
            document_id=self.document_id,
            status=self.status,
            queue_position=self.queue_position if self.status is JobStatus.QUEUED else None,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            cancellation_requested=self.cancellation_requested,
            failure_code=self.failure_code,
            failure_message=self.failure_message,
            attempt=self.attempt,
        )

"""Document domain contracts.

Phase 1 accepts and validates uploads but performs **no** extraction. Public
document summaries therefore always report ``result_available: false`` and
``extraction_performed: false``, and progress is capped at 5% (upload/queue
admission only).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from backend.app.contracts.base import ApiModel
from backend.app.contracts.identifiers import DocumentId, JobId

# Progress never exceeds this in Phase 1: no document has been extracted.
MAX_PHASE1_PROGRESS_PERCENT = 5


class DocumentFormat(StrEnum):
    """Canonical internal format key for a supported input type."""

    PDF = "pdf"
    DOC = "doc"
    DOCX = "docx"
    TXT = "txt"
    JPEG = "jpeg"
    PNG = "png"
    TIFF = "tiff"
    BMP = "bmp"
    WEBP = "webp"


class PageCountStatus(StrEnum):
    """Whether a document's page count is known in Phase 1."""

    KNOWN = "known"
    PENDING_CANONICALISATION = "pending_canonicalisation"


class DocumentStatus(StrEnum):
    """Lifecycle state of an accepted document during Phase 1."""

    UPLOADED = "uploaded"
    QUEUED = "queued"
    PREPARING = "preparing"
    READY_FOR_EXTRACTION = "ready_for_extraction"
    CANCELLED = "cancelled"
    FAILED = "failed"


class DocumentSummary(ApiModel):
    """Public summary of an accepted document."""

    document_id: DocumentId = Field(description="Opaque document identifier.")
    display_filename: str = Field(description="Sanitised display filename (never a storage path).")
    extension: str = Field(description="Lowercased, validated file extension without the dot.")
    format: DocumentFormat = Field(description="Canonical internal format key.")
    media_type: str = Field(description="Server-validated media type.")
    size_bytes: int = Field(ge=0, description="Accepted file size in bytes.")
    sha256: str = Field(min_length=64, max_length=64, description="Lowercase hex SHA-256 digest.")
    page_count: int | None = Field(default=None, ge=0, description="Known page count, else null.")
    page_count_status: PageCountStatus = Field(description="Whether the page count is known.")
    status: DocumentStatus = Field(description="Current document lifecycle status.")
    progress_percent: int = Field(
        ge=0,
        le=MAX_PHASE1_PROGRESS_PERCENT,
        description="Honest Phase 1 progress; capped at 5% (no extraction).",
    )
    result_available: bool = Field(default=False, description="Always false in Phase 1.")
    extraction_performed: bool = Field(default=False, description="Always false in Phase 1.")
    warning_count: int = Field(default=0, ge=0, description="Number of non-fatal upload warnings.")
    queue_position: int | None = Field(
        default=None, ge=1, description="Dynamic 1-based queue position while queued."
    )
    active_job_id: JobId | None = Field(
        default=None, description="Identifier of the active/last admission job, if any."
    )
    created_at: datetime = Field(description="Timezone-aware UTC acceptance time.")


class DocumentStatusCounts(ApiModel):
    """Counts of documents grouped by lifecycle status."""

    uploaded: int = Field(default=0, ge=0)
    queued: int = Field(default=0, ge=0)
    preparing: int = Field(default=0, ge=0)
    ready_for_extraction: int = Field(default=0, ge=0)
    cancelled: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)


class DocumentListResponse(ApiModel):
    """Response body for listing a session's documents."""

    documents: list[DocumentSummary] = Field(description="Documents in acceptance order.")

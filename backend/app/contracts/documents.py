"""Document domain contracts.

Phase 2 accepts and validates uploads, performs canonicalisation for a viewer
representation, but performs **no** extraction. Public document summaries
therefore always report ``result_available: false`` and
``extraction_performed: false``, and progress is capped at 15% (canonical view
ready).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from backend.app.contracts.base import ApiModel
from backend.app.contracts.canonical import CanonicalisationMethod, CanonicalStatus
from backend.app.contracts.identifiers import DocumentId, JobId

# Progress never exceeds this in Phase 2: no document has been extracted.
MAX_PHASE2_PROGRESS_PERCENT = 15
# Backward-compatible alias for Phase 1 references in tests/docs.
MAX_PHASE1_PROGRESS_PERCENT = MAX_PHASE2_PROGRESS_PERCENT


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
    """Lifecycle state of an accepted document during Phase 2."""

    UPLOADED = "uploaded"
    QUEUED = "queued"
    CANONICALISING = "canonicalising"
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
        le=MAX_PHASE2_PROGRESS_PERCENT,
        description="Honest Phase 2 progress; capped at 15% (no extraction).",
    )
    result_available: bool = Field(default=False, description="Always false in Phase 2.")
    extraction_performed: bool = Field(default=False, description="Always false in Phase 2.")
    warning_count: int = Field(default=0, ge=0, description="Number of non-fatal upload warnings.")
    queue_position: int | None = Field(
        default=None, ge=1, description="Dynamic 1-based queue position while queued."
    )
    active_job_id: JobId | None = Field(
        default=None, description="Identifier of the active/last admission job, if any."
    )
    created_at: datetime = Field(description="Timezone-aware UTC acceptance time.")
    canonical_status: CanonicalStatus | None = Field(
        default=None, description="Canonical view lifecycle status when known."
    )
    canonicalisation_method: CanonicalisationMethod | None = Field(
        default=None, description="Method used to produce the canonical PDF, when ready."
    )
    canonical_view_available: bool = Field(
        default=False, description="True when a canonical PDF is ready to serve."
    )
    canonical_view_url: str | None = Field(
        default=None, description="Relative URL for the canonical PDF viewer document."
    )
    canonical_metadata_url: str | None = Field(
        default=None, description="Relative URL for canonical page metadata."
    )


class DocumentStatusCounts(ApiModel):
    """Counts of documents grouped by lifecycle status."""

    uploaded: int = Field(default=0, ge=0)
    queued: int = Field(default=0, ge=0)
    canonicalising: int = Field(default=0, ge=0)
    ready_for_extraction: int = Field(default=0, ge=0)
    cancelled: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)


class DocumentListResponse(ApiModel):
    """Response body for listing a session's documents."""

    documents: list[DocumentSummary] = Field(description="Documents in acceptance order.")

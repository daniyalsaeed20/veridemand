"""Document domain contracts.

Phase 4 advances through canonicalisation, native trust, then printed visual OCR.
Public summaries always report ``result_available: false`` and
``extraction_performed: false`` (final extraction is not complete). Progress is
capped at 65% after visual OCR completes.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from backend.app.contracts.base import ApiModel
from backend.app.contracts.canonical import CanonicalisationMethod, CanonicalStatus
from backend.app.contracts.identifiers import DocumentId, JobId
from backend.app.contracts.native import DocumentSourcePolicy
from backend.app.contracts.routing import FinalRouteHistogram

# Progress never exceeds this in Phase 4: handwriting/LLM/structure remain later.
MAX_PHASE4_PROGRESS_PERCENT = 65
MAX_PHASE3_PROGRESS_PERCENT = 35
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
    """Lifecycle state of an accepted document during Phase 4."""

    UPLOADED = "uploaded"
    QUEUED = "queued"
    CANONICALISING = "canonicalising"
    READY_FOR_EXTRACTION = "ready_for_extraction"
    INSPECTING_NATIVE = "inspecting_native"
    EXTRACTING_NATIVE = "extracting_native"
    NATIVE_TRUST_COMPLETE = "native_trust_complete"
    VISUAL_PENDING = "visual_pending"
    VISUAL_PROCESSING = "visual_processing"
    VISUAL_PROCESSING_COMPLETE = "visual_processing_complete"
    VISUAL_PROCESSING_PARTIAL = "visual_processing_partial"
    VISUAL_PROCESSING_FAILED = "visual_processing_failed"
    AWAITING_PHASE_6 = "awaiting_phase_6"
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
        le=MAX_PHASE4_PROGRESS_PERCENT,
        description="Honest Phase 4 progress; capped at 65% (printed visual OCR complete).",
    )
    result_available: bool = Field(
        default=False, description="Always false until final extraction exists."
    )
    extraction_performed: bool = Field(
        default=False, description="Always false until final extraction exists."
    )
    native_extraction_performed: bool = Field(
        default=False, description="True when native candidate extraction ran."
    )
    native_result_available: bool = Field(
        default=False,
        description="True when at least one accepted native page remains after escalation.",
    )
    visual_processing_required: bool = Field(
        default=False, description="True when one or more pages require visual processing."
    )
    visual_processing_performed: bool = Field(
        default=False, description="True when Phase 4 visual OCR ran for selected pages."
    )
    visual_result_available: bool = Field(
        default=False, description="True when at least one visual OCR page result is published."
    )
    document_source_policy: DocumentSourcePolicy | None = Field(
        default=None, description="Document-level source authority after native/visual stages."
    )
    user_status_message: str | None = Field(
        default=None, description="Safe user-facing status for the current processing stage."
    )
    failure_stage: str | None = Field(
        default=None,
        description="Safe stage name when processing failed (e.g. extracting_native).",
    )
    failure_code: str | None = Field(
        default=None, description="Stable machine-readable failure code when status is failed."
    )
    failure_message: str | None = Field(
        default=None, description="Safe, non-sensitive failure message for operators."
    )
    failure_page_number: int | None = Field(
        default=None, ge=1, description="Affected page number when known."
    )
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
    native_summary_url: str | None = Field(
        default=None, description="Relative URL for the native extraction summary."
    )
    visual_summary_url: str | None = Field(
        default=None, description="Relative URL for the visual OCR summary."
    )
    pages_completed: int | None = Field(
        default=None, ge=0, description="Visual pages completed when processing."
    )
    pages_total: int | None = Field(
        default=None, ge=0, description="Visual pages selected for processing."
    )
    major_phase: str | None = Field(
        default=None,
        description=(
            "Current major processing phase (admission/canonicalisation/native_trust/visual_ocr)."
        ),
    )
    major_phase_percent: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Progress within the current major phase (0-100).",
    )
    page_percent: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Progress within the active visual page (0-100).",
    )
    active_page_number: int | None = Field(
        default=None, ge=1, description="Active visual page number when processing."
    )
    current_operation: str | None = Field(
        default=None, description="Stable operation identifier for the active stage."
    )
    operation_status: str | None = Field(
        default=None, description="Operation lifecycle status (started/running/completed/...)."
    )
    progress_kind: str | None = Field(
        default=None, description="determinate, indeterminate, or heartbeat."
    )
    elapsed_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Document-level elapsed seconds (alias of document_elapsed_seconds).",
    )
    document_elapsed_seconds: float | None = Field(
        default=None, ge=0.0, description="Monotonic elapsed seconds since the job started."
    )
    page_elapsed_seconds: float | None = Field(
        default=None, ge=0.0, description="Monotonic elapsed seconds for the active visual page."
    )
    operation_elapsed_seconds: float | None = Field(
        default=None, ge=0.0, description="Monotonic elapsed seconds for the active operation."
    )
    deadline_remaining_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Deprecated ambiguous deadline; prefer document_/page_/operation_/"
            "attempt_deadline_remaining_seconds."
        ),
    )
    worker_generation: int | None = Field(
        default=None, ge=0, description="OCR worker generation owning the active request."
    )
    worker_restart_count: int | None = Field(
        default=None, ge=0, description="OCR worker restarts since process start."
    )
    attempt_number: int | None = Field(
        default=None, ge=1, description="Current page/document attempt number."
    )
    max_attempts: int | None = Field(
        default=None, ge=1, description="Maximum attempts allowed for the active page."
    )
    stage_timeline: list[dict[str, object]] | None = Field(
        default=None,
        description="Bounded privacy-safe completed/active stage history for UI timelines.",
    )
    # Phase 4.5 live progress / route breakdown (optional).
    progress_version: int | None = Field(default=None, ge=1)
    current_route: str | None = Field(default=None)
    estimate_status: str | None = Field(default=None)
    estimate_confidence: str | None = Field(default=None)
    estimate_sample_count: int | None = Field(default=None, ge=0)
    estimated_document_remaining_seconds: float | None = Field(default=None, ge=0.0)
    estimated_queue_remaining_seconds: float | None = Field(default=None, ge=0.0)
    estimated_completion_at: datetime | None = Field(default=None)
    estimated_current_operation_seconds: float | None = Field(default=None, ge=0.0)
    estimated_current_page_seconds: float | None = Field(default=None, ge=0.0)
    average_page_seconds: float | None = Field(default=None, ge=0.0)
    average_full_ocr_page_seconds: float | None = Field(default=None, ge=0.0)
    pages_per_minute: float | None = Field(default=None, ge=0.0)
    document_pages_total: int | None = Field(default=None, ge=0)
    document_page_number: int | None = Field(default=None, ge=1)
    selected_page_index: int | None = Field(default=None, ge=1)
    selected_pages_total: int | None = Field(default=None, ge=0)
    visual_page_index: int | None = Field(default=None, ge=1)
    visual_pages_total: int | None = Field(default=None, ge=0)
    route_page_index: int | None = Field(default=None, ge=1)
    route_pages_total: int | None = Field(default=None, ge=0)
    operation_id: str | None = Field(default=None)
    native_pages_retained: int | None = Field(default=None, ge=0)
    native_pages_selected: int | None = Field(default=None, ge=0)
    native_pages_completed: int | None = Field(default=None, ge=0)
    embedded_verification_pages_selected: int | None = Field(default=None, ge=0)
    embedded_verification_pages_completed: int | None = Field(default=None, ge=0)
    embedded_ocr_pages_verified: int | None = Field(default=None, ge=0)
    targeted_repair_pages_selected: int | None = Field(default=None, ge=0)
    targeted_repair_pages_completed: int | None = Field(default=None, ge=0)
    full_ocr_pages_selected: int | None = Field(default=None, ge=0)
    full_ocr_pages_completed: int | None = Field(default=None, ge=0)
    full_ocr_pages_remaining: int | None = Field(default=None, ge=0)
    final_route_histogram: FinalRouteHistogram | None = Field(
        default=None,
        description="Exclusive terminal route histogram when known.",
    )
    visual_no_text_pages: int | None = Field(default=None, ge=0)
    failed_pages: int | None = Field(default=None, ge=0)
    pages_terminal_total: int | None = Field(default=None, ge=0)
    pages_remaining: int | None = Field(default=None, ge=0)
    fair_scheduling_enabled: bool | None = Field(default=None)
    scheduler_document_state: str | None = Field(default=None)
    scheduler_priority_class: str | None = Field(default=None)
    scheduler_effective_priority: int | None = Field(default=None, ge=0)
    scheduler_queue_position: int | None = Field(default=None, ge=1)
    scheduler_turn_number: int | None = Field(default=None, ge=0)
    scheduler_quantum: int | None = Field(default=None, ge=0)
    scheduler_quantum_completed: int | None = Field(default=None, ge=0)
    scheduler_remaining_work_units: int | None = Field(default=None, ge=0)
    scheduler_waiting_seconds: float | None = Field(default=None, ge=0.0)
    scheduler_turns_skipped: int | None = Field(default=None, ge=0)
    estimated_next_turn_seconds: float | None = Field(default=None, ge=0.0)
    estimated_waiting_seconds: float | None = Field(default=None, ge=0.0)
    document_started_at: datetime | None = Field(default=None)
    phase_started_at: datetime | None = Field(default=None)
    page_started_at: datetime | None = Field(default=None)
    operation_started_at: datetime | None = Field(default=None)
    phase_elapsed_seconds: float | None = Field(default=None, ge=0.0)
    server_timestamp: datetime | None = Field(default=None)
    batch_elapsed_seconds: float | None = Field(default=None, ge=0.0)
    attempt_elapsed_seconds: float | None = Field(default=None, ge=0.0)
    batch_started_at_timestamp: datetime | None = Field(default=None)
    document_started_at_timestamp: datetime | None = Field(default=None)
    document_deadline_remaining_seconds: float | None = Field(default=None, ge=0.0)
    page_deadline_remaining_seconds: float | None = Field(default=None, ge=0.0)
    operation_deadline_remaining_seconds: float | None = Field(default=None, ge=0.0)
    attempt_deadline_remaining_seconds: float | None = Field(default=None, ge=0.0)
    slow_warning_status: str | None = Field(default=None)
    slow_warning_operation_id: str | None = Field(default=None)
    slow_warning_started_at: datetime | None = Field(default=None)
    slow_warning_threshold_seconds: float | None = Field(default=None, ge=0.0)
    slow_warning_reason: str | None = Field(default=None)
    estimated_batch_remaining_seconds: float | None = Field(default=None, ge=0.0)
    estimated_batch_completion_at: datetime | None = Field(default=None)
    estimated_document_completion_at: datetime | None = Field(default=None)


class DocumentStatusCounts(ApiModel):
    """Counts of documents grouped by lifecycle status."""

    uploaded: int = Field(default=0, ge=0)
    queued: int = Field(default=0, ge=0)
    canonicalising: int = Field(default=0, ge=0)
    ready_for_extraction: int = Field(default=0, ge=0)
    inspecting_native: int = Field(default=0, ge=0)
    extracting_native: int = Field(default=0, ge=0)
    native_trust_complete: int = Field(default=0, ge=0)
    visual_pending: int = Field(default=0, ge=0)
    visual_processing: int = Field(default=0, ge=0)
    visual_processing_complete: int = Field(default=0, ge=0)
    visual_processing_partial: int = Field(default=0, ge=0)
    visual_processing_failed: int = Field(default=0, ge=0)
    awaiting_phase_6: int = Field(default=0, ge=0)
    cancelled: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)


class DocumentListResponse(ApiModel):
    """Response body for listing a session's documents."""

    documents: list[DocumentSummary] = Field(description="Documents in acceptance order.")

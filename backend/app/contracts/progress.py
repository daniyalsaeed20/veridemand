"""Progress event contract for the Server-Sent Events stream.

``ProgressEvent`` is the single, strict shape delivered over SSE and embedded in
the session snapshot (so it is exported to OpenAPI and generated as a reusable
frontend Zod schema). Extraction-stage event types are *reserved* here but never
emitted in Phase 1.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from backend.app.contracts.base import ApiModel
from backend.app.contracts.documents import DocumentStatus
from backend.app.contracts.identifiers import DocumentId, EventId, JobId, SessionId
from backend.app.contracts.jobs import JobStatus
from backend.app.contracts.routing import FinalRouteHistogram


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
    DOCUMENT_AWAITING_PHASE_6 = "document.awaiting_phase_6"

    # Phase 4.5 hybrid routing / throughput progress.
    DOCUMENT_PAGE_ROUTE_STARTED = "document.page_route_started"
    DOCUMENT_PAGE_ROUTE_COMPLETED = "document.page_route_completed"
    DOCUMENT_EMBEDDED_OCR_VISUAL_CHECK_STARTED = "document.embedded_ocr_visual_check_started"
    DOCUMENT_EMBEDDED_OCR_VISUAL_CHECK_COMPLETED = "document.embedded_ocr_visual_check_completed"
    DOCUMENT_EMBEDDED_OCR_RECOGNITION_CHECK_STARTED = (
        "document.embedded_ocr_recognition_check_started"
    )
    DOCUMENT_EMBEDDED_OCR_RECOGNITION_CHECK_COMPLETED = (
        "document.embedded_ocr_recognition_check_completed"
    )
    DOCUMENT_EMBEDDED_OCR_VERIFIED = "document.embedded_ocr_verified"
    DOCUMENT_EMBEDDED_OCR_TARGETED_REPAIR_STARTED = "document.embedded_ocr_targeted_repair_started"
    DOCUMENT_EMBEDDED_OCR_TARGETED_REPAIR_COMPLETED = (
        "document.embedded_ocr_targeted_repair_completed"
    )
    DOCUMENT_FULL_OCR_PRIMARY_STARTED = "document.full_ocr_primary_started"
    DOCUMENT_FULL_OCR_PRIMARY_COMPLETED = "document.full_ocr_primary_completed"
    DOCUMENT_FULL_OCR_QUALITY_EVALUATION_STARTED = "document.full_ocr_quality_evaluation_started"
    DOCUMENT_FULL_OCR_QUALITY_EVALUATION_COMPLETED = (
        "document.full_ocr_quality_evaluation_completed"
    )
    DOCUMENT_FULL_OCR_FALLBACK_STARTED = "document.full_ocr_fallback_started"
    DOCUMENT_FULL_OCR_FALLBACK_COMPLETED = "document.full_ocr_fallback_completed"
    DOCUMENT_FULL_OCR_RESULT_SELECTION_STARTED = "document.full_ocr_result_selection_started"
    DOCUMENT_FULL_OCR_RESULT_SELECTION_COMPLETED = "document.full_ocr_result_selection_completed"
    DOCUMENT_VISUAL_NO_TEXT_COMPLETED = "document.visual_no_text_completed"

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

    # Correction 7 — fair document scheduling events.
    SCHEDULER_DOCUMENT_ADMITTED = "scheduler.document_admitted"
    SCHEDULER_DOCUMENT_READY = "scheduler.document_ready"
    SCHEDULER_TURN_STARTED = "scheduler.turn_started"
    SCHEDULER_QUANTUM_COMPLETED = "scheduler.quantum_completed"
    SCHEDULER_DOCUMENT_YIELDED = "scheduler.document_yielded"
    SCHEDULER_DOCUMENT_CHECKPOINTED = "scheduler.document_checkpointed"
    SCHEDULER_PRIORITY_CHANGED = "scheduler.priority_changed"
    SCHEDULER_DOCUMENT_RESUMED = "scheduler.document_resumed"
    SCHEDULER_DOCUMENT_TERMINAL = "scheduler.document_terminal"

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
    page_number: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Deprecated: absolute document page when set. Prefer document_page_number. "
            "Must not be paired with a selected-work pages_total denominator."
        ),
    )
    pages_completed: int | None = Field(
        default=None,
        ge=0,
        description="Deprecated: prefer route-specific *_pages_completed counters.",
    )
    pages_total: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Deprecated: ambiguous denominator. Prefer document_pages_total or "
            "selected_pages_total / visual_pages_total."
        ),
    )
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
    deadline_remaining_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Deprecated: ambiguous single deadline. Prefer document_/page_/operation_/"
            "attempt_deadline_remaining_seconds."
        ),
    )
    worker_pid: int | None = Field(default=None, ge=0)
    worker_generation: int | None = Field(default=None, ge=0)
    worker_restart_count: int | None = Field(default=None, ge=0)
    attempt_number: int | None = Field(default=None, ge=1)
    max_attempts: int | None = Field(default=None, ge=1)
    reason_code: str | None = Field(default=None, description="Safe reason/error code.")
    operation_id: str | None = Field(
        default=None, description="Stable operation-attempt identity for lifecycle events."
    )
    # Canonical page / selected-work indices (Correction 4).
    document_page_number: int | None = Field(
        default=None, ge=1, description="Absolute 1-based page in the canonical document."
    )
    selected_page_index: int | None = Field(
        default=None,
        ge=1,
        description="1-based position within pages selected for the current work category.",
    )
    selected_pages_total: int | None = Field(
        default=None, ge=0, description="Count of pages selected for the current work category."
    )
    visual_page_index: int | None = Field(
        default=None, ge=1, description="1-based index within selected visual OCR pages."
    )
    visual_pages_total: int | None = Field(
        default=None, ge=0, description="Selected visual OCR page count."
    )
    route_page_index: int | None = Field(
        default=None, ge=1, description="1-based index within the active route category."
    )
    route_pages_total: int | None = Field(
        default=None, ge=0, description="Page count for the active route category."
    )
    # Optional document-level visual selection / ETA fields (absent until known).
    document_pages_total: int | None = Field(default=None, ge=0)
    native_pages_retained: int | None = Field(default=None, ge=0)
    native_pages_selected: int | None = Field(default=None, ge=0)
    native_pages_completed: int | None = Field(default=None, ge=0)
    embedded_verification_pages_selected: int | None = Field(default=None, ge=0)
    embedded_verification_pages_completed: int | None = Field(default=None, ge=0)
    visual_pages_selected: int | None = Field(default=None, ge=0)
    visual_pages_completed: int | None = Field(default=None, ge=0)
    visual_pages_remaining: int | None = Field(default=None, ge=0)
    visual_no_text_pages: int | None = Field(default=None, ge=0)
    failed_pages: int | None = Field(default=None, ge=0)
    pages_terminal_total: int | None = Field(default=None, ge=0)
    pages_per_minute: float | None = Field(default=None, ge=0.0)
    average_page_seconds: float | None = Field(default=None, ge=0.0)
    estimated_document_seconds_remaining: float | None = Field(default=None, ge=0.0)
    estimated_queue_seconds_remaining: float | None = Field(default=None, ge=0.0)
    estimated_completion_time: datetime | None = Field(default=None)
    estimate_confidence: str | None = Field(default=None)
    # Phase 4.5 live progress / ETA extensions (all optional).
    progress_version: int | None = Field(default=None, ge=1)
    server_timestamp: datetime | None = Field(default=None)
    document_started_at: datetime | None = Field(default=None)
    phase_started_at: datetime | None = Field(default=None)
    page_started_at: datetime | None = Field(default=None)
    operation_started_at: datetime | None = Field(default=None)
    phase_elapsed_seconds: float | None = Field(default=None, ge=0.0)
    estimated_current_operation_seconds: float | None = Field(default=None, ge=0.0)
    estimated_current_page_seconds: float | None = Field(default=None, ge=0.0)
    estimated_document_remaining_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Alias of estimated_document_seconds_remaining.",
    )
    estimated_queue_remaining_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Alias of estimated_queue_seconds_remaining.",
    )
    estimated_completion_at: datetime | None = Field(
        default=None,
        description="Alias of estimated_completion_time.",
    )
    estimate_status: str | None = Field(default=None)
    estimate_sample_count: int | None = Field(default=None, ge=0)
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
    queue_documents_total: int | None = Field(default=None, ge=0)
    queue_documents_completed: int | None = Field(default=None, ge=0)
    queue_documents_remaining: int | None = Field(default=None, ge=0)
    active_document_position: int | None = Field(default=None, ge=1)
    current_route: str | None = Field(default=None)
    current_operation: str | None = Field(default=None, description="Alias of operation when set.")
    current_page: int | None = Field(default=None, ge=1)
    current_page_total: int | None = Field(default=None, ge=0)
    route: str | None = Field(default=None, description="Page route for route events.")
    average_full_ocr_page_seconds: float | None = Field(default=None, ge=0.0)
    fair_scheduling_enabled: bool | None = Field(default=None)
    # Correction 7 — scheduler turn/position/quantum fields.
    scheduler_turn_number: int | None = Field(default=None, ge=0)
    scheduler_queue_position: int | None = Field(default=None, ge=1)
    scheduler_priority_class: str | None = Field(default=None)
    scheduler_effective_priority: int | None = Field(default=None, ge=0)
    scheduler_quantum: int | None = Field(default=None, ge=0)
    scheduler_quantum_completed: int | None = Field(default=None, ge=0)
    scheduler_remaining_work_units: int | None = Field(default=None, ge=0)
    scheduler_document_state: str | None = Field(default=None)
    scheduler_reason: str | None = Field(default=None)
    scheduler_waiting_seconds: float | None = Field(default=None, ge=0.0)
    scheduler_turns_skipped: int | None = Field(default=None, ge=0)
    estimated_next_turn_seconds: float | None = Field(default=None, ge=0.0)
    estimated_waiting_seconds: float | None = Field(default=None, ge=0.0)
    # Correction 4 clocks, deadlines, slow warning, batch ETA.
    batch_elapsed_seconds: float | None = Field(default=None, ge=0.0)
    attempt_elapsed_seconds: float | None = Field(default=None, ge=0.0)
    batch_started_at_timestamp: datetime | None = Field(default=None)
    document_started_at_timestamp: datetime | None = Field(default=None)
    document_deadline_remaining_seconds: float | None = Field(default=None, ge=0.0)
    page_deadline_remaining_seconds: float | None = Field(default=None, ge=0.0)
    operation_deadline_remaining_seconds: float | None = Field(default=None, ge=0.0)
    attempt_deadline_remaining_seconds: float | None = Field(default=None, ge=0.0)
    slow_warning_status: str | None = Field(
        default=None,
        description="inactive|approaching_threshold|active|resolved",
    )
    slow_warning_operation_id: str | None = Field(default=None)
    slow_warning_started_at: datetime | None = Field(default=None)
    slow_warning_threshold_seconds: float | None = Field(default=None, ge=0.0)
    slow_warning_reason: str | None = Field(default=None)
    estimated_batch_remaining_seconds: float | None = Field(default=None, ge=0.0)
    estimated_batch_completion_at: datetime | None = Field(default=None)
    estimated_document_completion_at: datetime | None = Field(
        default=None,
        description="Alias of estimated_completion_at for document scope.",
    )

    @model_validator(mode="after")
    def _validate_progress_consistency(self) -> ProgressEvent:
        def _index_total(index: int | None, total: int | None, label: str) -> None:
            if index is None:
                return
            if total is None or total <= 0:
                raise ValueError(f"{label}_total must be positive when {label} index is set")
            if index > total:
                raise ValueError(f"{label} index cannot exceed total")

        _index_total(self.document_page_number, self.document_pages_total, "document_page")
        _index_total(self.selected_page_index, self.selected_pages_total, "selected_page")
        _index_total(self.visual_page_index, self.visual_pages_total, "visual_page")
        _index_total(self.route_page_index, self.route_pages_total, "route_page")

        if (
            self.full_ocr_pages_completed is not None
            and self.full_ocr_pages_selected is not None
            and self.full_ocr_pages_completed > self.full_ocr_pages_selected
        ):
            raise ValueError("full_ocr_pages_completed cannot exceed full_ocr_pages_selected")
        if (
            self.targeted_repair_pages_completed is not None
            and self.targeted_repair_pages_selected is not None
            and self.targeted_repair_pages_completed > self.targeted_repair_pages_selected
        ):
            raise ValueError(
                "targeted_repair_pages_completed cannot exceed targeted_repair_pages_selected"
            )
        if (
            self.native_pages_completed is not None
            and self.native_pages_selected is not None
            and self.native_pages_completed > self.native_pages_selected
        ):
            raise ValueError("native_pages_completed cannot exceed native_pages_selected")
        if (
            self.embedded_verification_pages_completed is not None
            and self.embedded_verification_pages_selected is not None
            and self.embedded_verification_pages_completed
            > self.embedded_verification_pages_selected
        ):
            raise ValueError(
                "embedded_verification_pages_completed cannot exceed "
                "embedded_verification_pages_selected"
            )

        for name in (
            "batch_elapsed_seconds",
            "document_elapsed_seconds",
            "phase_elapsed_seconds",
            "page_elapsed_seconds",
            "operation_elapsed_seconds",
            "attempt_elapsed_seconds",
            "document_deadline_remaining_seconds",
            "page_deadline_remaining_seconds",
            "operation_deadline_remaining_seconds",
            "attempt_deadline_remaining_seconds",
            "deadline_remaining_seconds",
        ):
            value = getattr(self, name)
            if value is not None and not (value == value):  # NaN check
                raise ValueError(f"{name} must be finite")

        return self

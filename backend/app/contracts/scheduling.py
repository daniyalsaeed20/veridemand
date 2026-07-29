"""Fair document scheduling contracts (Correction 7)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from backend.app.contracts.base import ApiModel
from backend.app.contracts.identifiers import DocumentId, SessionId


class WorkClass(StrEnum):
    NATIVE_DOCUMENT_WORK = "native_document_work"
    EMBEDDED_VERIFICATION_PAGE = "embedded_verification_page"
    TARGETED_REPAIR_PAGE = "targeted_repair_page"
    FULL_OCR_PAGE = "full_ocr_page"
    SUMMARY_RECONCILIATION = "summary_reconciliation"


class PriorityClass(StrEnum):
    INTERACTIVE_SHORT = "interactive_short"
    NORMAL = "normal"
    LARGE_BACKGROUND = "large_background"


class SchedulingDocumentState(StrEnum):
    NOT_ADMITTED = "not_admitted"
    READY = "ready"
    RUNNING = "running"
    YIELDING = "yielding"
    CHECKPOINTED = "checkpointed"
    BLOCKED = "blocked"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkUnitStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class ProcessingWorkUnit(ApiModel):
    work_unit_id: str
    session_id: SessionId
    document_id: DocumentId
    route: str
    work_class: WorkClass
    document_page_number: int = Field(ge=1)
    document_pages_total: int = Field(ge=1)
    selected_page_index: int = Field(ge=1)
    selected_pages_total: int = Field(ge=1)
    repair_region_start_index: int | None = Field(default=None, ge=0)
    repair_region_end_index: int | None = Field(default=None, ge=0)
    priority_class: PriorityClass
    priority_value: int = 0
    admitted_sequence: int = Field(ge=1)
    document_turn_sequence: int = Field(default=0, ge=0)
    work_unit_sequence: int = Field(ge=1)
    attempt_number: int = Field(default=1, ge=1)
    worker_generation: int | None = Field(default=None, ge=0)
    estimated_cost_class: str | None = None
    estimated_duration_seconds: float | None = Field(default=None, ge=0.0)
    status: WorkUnitStatus = WorkUnitStatus.PENDING
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    checkpoint_version: int = Field(default=0, ge=0)
    policy_version: str = "correction7-v1"


class DocumentSchedulingState(ApiModel):
    document_id: DocumentId
    session_id: SessionId
    state: SchedulingDocumentState
    priority_class: PriorityClass
    effective_priority: int = 0
    queue_position: int | None = Field(default=None, ge=1)
    turn_number: int = Field(default=0, ge=0)
    last_turn_at: datetime | None = None
    turns_completed: int = Field(default=0, ge=0)
    turns_skipped: int = Field(default=0, ge=0)
    current_quantum: int = Field(default=0, ge=0)
    quantum_completed: int = Field(default=0, ge=0)
    quantum_remaining: int = Field(default=0, ge=0)
    remaining_native_work: int = Field(default=0, ge=0)
    remaining_embedded_work: int = Field(default=0, ge=0)
    remaining_repair_pages: int = Field(default=0, ge=0)
    remaining_full_ocr_pages: int = Field(default=0, ge=0)
    waiting_seconds: float = Field(default=0.0, ge=0.0)
    aging_adjustment: int = Field(default=0, ge=0)
    next_eligible_turn: int = Field(default=0, ge=0)
    admitted_at: datetime
    last_checkpoint_version: int = Field(default=0, ge=0)
    estimated_document_remaining_seconds: float | None = Field(default=None, ge=0.0)
    estimated_next_turn_seconds: float | None = Field(default=None, ge=0.0)


class SchedulerSnapshot(ApiModel):
    scheduler_enabled: bool
    scheduler_policy_version: str
    active_document_id: DocumentId | None = None
    active_work_unit_id: str | None = None
    ready_document_count: int = Field(default=0, ge=0)
    checkpointed_document_count: int = Field(default=0, ge=0)
    turn_number: int = Field(default=0, ge=0)
    documents: list[DocumentSchedulingState] = Field(default_factory=list)
    estimated_batch_remaining_seconds: float | None = Field(default=None, ge=0.0)


class QueuePosition(ApiModel):
    document_id: DocumentId
    position: int = Field(ge=1)
    priority_class: PriorityClass
    effective_priority: int = 0
    estimated_next_turn_seconds: float | None = Field(default=None, ge=0.0)


class PriorityChangeRequest(ApiModel):
    action: str = Field(description="move_ahead|move_behind|restore_default_priority")
    reason: str | None = None


class PriorityChangeResponse(ApiModel):
    document_id: DocumentId
    action: str
    success: bool
    message: str
    old_priority_class: PriorityClass | None = None
    new_priority_class: PriorityClass | None = None
    old_effective_priority: int | None = None
    new_effective_priority: int | None = None
    effective_next_turn: int | None = Field(default=None, ge=0)


class WorkloadEstimate(ApiModel):
    document_id: DocumentId
    estimated_active_work_seconds: float | None = Field(default=None, ge=0.0)
    estimated_waiting_seconds: float | None = Field(default=None, ge=0.0)
    estimated_document_remaining_seconds: float | None = Field(default=None, ge=0.0)
    estimated_batch_remaining_seconds: float | None = Field(default=None, ge=0.0)
    estimated_next_turn_seconds: float | None = Field(default=None, ge=0.0)
    confidence: str | None = Field(default=None, description="high|medium|low|unavailable")

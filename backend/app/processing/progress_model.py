"""Deterministic Phase 4 three-level progress (overall / phase / page).

Overall is capped at 65%. Progress is monotonic and never advanced by heartbeats.

Visual page processing maps into the 41-63 band via selected visual workload
fraction (not ambiguous document-page / selected-total mixing). Overall reaches
65 only after summary publication and authority reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from time import monotonic
from uuid import uuid4

from backend.app.processing.operation_lifecycle import (
    LifecycleRejectReason,
    OperationAttemptId,
    OperationLifecycleLedger,
)
from backend.app.processing.progress_weights import (
    OVERALL_CAP,
    OVERALL_PAGE_PROCESSING_END,
    OVERALL_PAGE_PROCESSING_START,
    OVERALL_PAGE_PROCESSING_WIDTH,
    OVERALL_SUMMARY_MID,
    OVERALL_SUMMARY_START,
)


class MajorPhase(StrEnum):
    ADMISSION = "admission"
    CANONICALISATION = "canonicalisation"
    NATIVE_TRUST = "native_trust"
    VISUAL_OCR = "visual_ocr"


class ProgressKind(StrEnum):
    DETERMINATE = "determinate"
    INDETERMINATE = "indeterminate"
    HEARTBEAT = "heartbeat"


class OperationStatus(StrEnum):
    QUEUED = "queued"
    STARTED = "started"
    RUNNING = "running"
    HEARTBEAT = "heartbeat"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    RETRYING = "retrying"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class SlowWarningStatus(StrEnum):
    INACTIVE = "inactive"
    APPROACHING_THRESHOLD = "approaching_threshold"
    ACTIVE = "active"
    RESOLVED = "resolved"


# Overall map — stage end boundaries.
OVERALL_JOB_ADMISSION_END = 2.0
OVERALL_CANONICAL_STAGING_END = 5.0
OVERALL_CANONICAL_END = 15.0
OVERALL_NATIVE_STRUCT_END = 17.0
OVERALL_NATIVE_EXTRACT_END = 32.0
OVERALL_NATIVE_POLICY_END = 35.0
OVERALL_VISUAL_SELECT_END = 37.0
OVERALL_VISIBILITY_END = 41.0

# Visual phase derives from overall relative to the 35-65 visual band.
OVERALL_VISUAL_BAND_START = 35.0
OVERALL_VISUAL_BAND_WIDTH = 30.0

# Deprecated aliases kept for import compatibility.
OVERALL_VISUAL_BAND_START_LEGACY = OVERALL_VISUAL_BAND_START
OVERALL_VISUAL_BAND_WIDTH_LEGACY = OVERALL_VISUAL_BAND_WIDTH

_TERMINAL_STATUSES = frozenset(
    {
        OperationStatus.COMPLETED,
        OperationStatus.FAILED,
        OperationStatus.TIMED_OUT,
        OperationStatus.CANCELLED,
        OperationStatus.SKIPPED,
    }
)

DEFAULT_SLOW_WARNING_THRESHOLD_SECONDS = 30.0


@dataclass
class ProgressSnapshot:
    overall_percent: float = 0.0
    major_phase: MajorPhase = MajorPhase.ADMISSION
    major_phase_percent: float = 0.0
    # Absolute document page (canonical).
    document_page_number: int | None = None
    document_pages_total: int | None = None
    # Selected-work indices (1-based within current work category).
    selected_page_index: int | None = None
    selected_pages_total: int = 0
    visual_page_index: int | None = None
    visual_pages_total: int = 0
    route_page_index: int | None = None
    route_pages_total: int | None = None
    # Legacy aliases — page_number is document page; pages_total is selected count.
    page_number: int | None = None
    pages_total: int | None = None
    pages_completed: int = 0
    pages_selected: int = 0
    page_percent: float | None = None
    operation: str = "job_admission"
    operation_id: str | None = None
    operation_status: OperationStatus = OperationStatus.QUEUED
    progress_kind: ProgressKind = ProgressKind.DETERMINATE
    elapsed_seconds: float = 0.0
    batch_elapsed_seconds: float = 0.0
    document_elapsed_seconds: float = 0.0
    phase_elapsed_seconds: float = 0.0
    page_elapsed_seconds: float | None = None
    operation_elapsed_seconds: float = 0.0
    attempt_elapsed_seconds: float = 0.0
    stage_elapsed_seconds: float = 0.0
    deadline_remaining_seconds: float | None = None
    document_deadline_remaining_seconds: float | None = None
    page_deadline_remaining_seconds: float | None = None
    operation_deadline_remaining_seconds: float | None = None
    attempt_deadline_remaining_seconds: float | None = None
    worker_pid: int | None = None
    worker_generation: int | None = None
    worker_restart_count: int = 0
    attempt_number: int = 1
    max_attempts: int = 2
    last_real_progress_at: float = field(default_factory=monotonic)
    last_heartbeat_at: float | None = None
    reason_code: str | None = None
    safe_message: str | None = None
    batch_started_at: float = field(default_factory=monotonic)
    job_started_at: float = field(default_factory=monotonic)
    phase_started_at_mono: float = field(default_factory=monotonic)
    stage_started_at: float = field(default_factory=monotonic)
    attempt_started_at: float = field(default_factory=monotonic)
    page_started_at: float | None = None
    operation_deadline_mono: float | None = None
    attempt_deadline_mono: float | None = None
    document_deadline_mono: float | None = None
    page_deadline_mono: float | None = None
    history: list[dict[str, object]] = field(default_factory=list)
    _operation_open: bool = False
    ledger: OperationLifecycleLedger = field(default_factory=OperationLifecycleLedger)
    last_lifecycle_reject: LifecycleRejectReason | None = None
    slow_warning_status: SlowWarningStatus = SlowWarningStatus.INACTIVE
    slow_warning_operation_id: str | None = None
    slow_warning_started_at: datetime | None = None
    slow_warning_threshold_seconds: float = DEFAULT_SLOW_WARNING_THRESHOLD_SECONDS
    slow_warning_reason: str | None = None
    document_id: str | None = None

    @property
    def operation_is_open(self) -> bool:
        return self._operation_open

    def bump_overall(self, target: float) -> None:
        self.overall_percent = min(OVERALL_CAP, max(self.overall_percent, target))
        self._sync_visual_phase_percent()

    def _sync_visual_phase_percent(self) -> None:
        if self.major_phase is not MajorPhase.VISUAL_OCR:
            return
        raw = (self.overall_percent - OVERALL_VISUAL_BAND_START) / OVERALL_VISUAL_BAND_WIDTH * 100.0
        phase = max(0.0, min(100.0, raw))
        self.major_phase_percent = max(self.major_phase_percent, phase)

    def _refresh_elapsed(self, *, now: float | None = None) -> None:
        instant = monotonic() if now is None else now
        self.batch_elapsed_seconds = instant - self.batch_started_at
        self.document_elapsed_seconds = instant - self.job_started_at
        self.elapsed_seconds = self.document_elapsed_seconds
        self.phase_elapsed_seconds = instant - self.phase_started_at_mono
        self.operation_elapsed_seconds = instant - self.stage_started_at
        self.stage_elapsed_seconds = self.operation_elapsed_seconds
        self.attempt_elapsed_seconds = instant - self.attempt_started_at
        if self.page_started_at is not None:
            self.page_elapsed_seconds = instant - self.page_started_at
        else:
            self.page_elapsed_seconds = None
        self._refresh_deadlines(now=instant)
        self._refresh_slow_warning(now=instant)

    def _remaining(self, deadline_mono: float | None, now: float) -> float | None:
        if deadline_mono is None:
            return None
        return max(0.0, deadline_mono - now)

    def _refresh_deadlines(self, *, now: float) -> None:
        self.document_deadline_remaining_seconds = self._remaining(self.document_deadline_mono, now)
        self.page_deadline_remaining_seconds = self._remaining(self.page_deadline_mono, now)
        self.operation_deadline_remaining_seconds = self._remaining(
            self.operation_deadline_mono, now
        )
        self.attempt_deadline_remaining_seconds = self._remaining(self.attempt_deadline_mono, now)
        # Deprecated single field: most specific active deadline.
        for value in (
            self.attempt_deadline_remaining_seconds,
            self.operation_deadline_remaining_seconds,
            self.page_deadline_remaining_seconds,
            self.document_deadline_remaining_seconds,
        ):
            if value is not None:
                self.deadline_remaining_seconds = value
                break
        else:
            # Preserve a manually assigned legacy value when no mono clocks exist
            # (unit tests and pre-Correction-4 callers).
            if any(
                deadline is not None
                for deadline in (
                    self.document_deadline_mono,
                    self.page_deadline_mono,
                    self.operation_deadline_mono,
                    self.attempt_deadline_mono,
                )
            ):
                self.deadline_remaining_seconds = None

    def _refresh_slow_warning(self, *, now: float) -> None:
        if not self._operation_open or self.operation_status in _TERMINAL_STATUSES:
            if self.slow_warning_status in {
                SlowWarningStatus.ACTIVE,
                SlowWarningStatus.APPROACHING_THRESHOLD,
            }:
                self.slow_warning_status = SlowWarningStatus.RESOLVED
            return
        elapsed = now - self.stage_started_at
        threshold = self.slow_warning_threshold_seconds
        approaching = threshold * 0.8
        if elapsed >= threshold:
            if self.slow_warning_status is not SlowWarningStatus.ACTIVE:
                self.slow_warning_status = SlowWarningStatus.ACTIVE
                self.slow_warning_operation_id = self.operation_id
                self.slow_warning_started_at = datetime.now(UTC)
                self.slow_warning_reason = "operation_exceeded_threshold"
        elif elapsed >= approaching and self.slow_warning_status is SlowWarningStatus.INACTIVE:
            self.slow_warning_status = SlowWarningStatus.APPROACHING_THRESHOLD
            self.slow_warning_operation_id = self.operation_id
            self.slow_warning_started_at = datetime.now(UTC)
            self.slow_warning_reason = "operation_approaching_threshold"

    def clear_slow_warning(self) -> None:
        was_active = self.slow_warning_status in {
            SlowWarningStatus.ACTIVE,
            SlowWarningStatus.APPROACHING_THRESHOLD,
        }
        self.slow_warning_status = (
            SlowWarningStatus.RESOLVED if was_active else SlowWarningStatus.INACTIVE
        )
        self.slow_warning_operation_id = None
        self.slow_warning_started_at = None
        self.slow_warning_reason = None

    def mark_real_progress(self) -> None:
        now = monotonic()
        self.last_real_progress_at = now
        self._refresh_elapsed(now=now)

    def mark_heartbeat(self) -> None:
        now = monotonic()
        self.last_heartbeat_at = now
        if self.operation_id and self.document_id:
            attempt = self._current_attempt_id()
            if attempt is not None:
                decision = self.ledger.register_heartbeat(attempt)
                if not decision.accepted:
                    self.last_lifecycle_reject = decision.reason
                    self._refresh_elapsed(now=now)
                    return
        self.operation_status = OperationStatus.HEARTBEAT
        self._refresh_elapsed(now=now)

    def begin_phase(self, phase: MajorPhase) -> None:
        self.major_phase = phase
        self.phase_started_at_mono = monotonic()
        self.phase_elapsed_seconds = 0.0

    def begin_page(
        self,
        document_page_number: int,
        *,
        selected_page_index: int | None = None,
        selected_pages_total: int | None = None,
        visual_page_index: int | None = None,
        visual_pages_total: int | None = None,
        route_page_index: int | None = None,
        route_pages_total: int | None = None,
        page_deadline_mono: float | None = None,
    ) -> None:
        self.document_page_number = document_page_number
        self.page_number = document_page_number  # legacy alias = document page
        if selected_page_index is not None:
            self.selected_page_index = selected_page_index
        if selected_pages_total is not None:
            self.selected_pages_total = selected_pages_total
            self.pages_selected = selected_pages_total
            self.pages_total = selected_pages_total  # legacy selected denominator
        if visual_page_index is not None:
            self.visual_page_index = visual_page_index
        if visual_pages_total is not None:
            self.visual_pages_total = visual_pages_total
        if route_page_index is not None:
            self.route_page_index = route_page_index
        if route_pages_total is not None:
            self.route_pages_total = route_pages_total
        self.page_started_at = monotonic()
        self.page_elapsed_seconds = 0.0
        self.page_deadline_mono = page_deadline_mono
        self.operation_deadline_mono = None
        self.clear_slow_warning()
        self.slow_warning_status = SlowWarningStatus.INACTIVE

    def _current_attempt_id(self) -> OperationAttemptId | None:
        if self.operation_id is None or self.document_id is None:
            return None
        return OperationAttemptId(
            operation_id=self.operation_id,
            document_id=self.document_id,
            operation=self.operation,
            attempt_number=self.attempt_number,
            worker_generation=self.worker_generation,
            document_page_number=self.document_page_number,
        )

    def begin_operation(
        self,
        operation: str,
        *,
        status: OperationStatus = OperationStatus.STARTED,
        attempt_number: int | None = None,
        operation_deadline_seconds: float | None = None,
        allow_replace_open: bool = False,
    ) -> bool:
        """Start a new operation attempt. Returns False if rejected by ledger."""

        if self._operation_open and not allow_replace_open:
            # Do not silently fabricate a completed terminal for a different op.
            self.last_lifecycle_reject = LifecycleRejectReason.INVALID_TRANSITION
            return False

        if attempt_number is not None:
            self.attempt_number = attempt_number

        self.operation = operation
        self.operation_id = (
            f"{operation}:{self.document_page_number or 0}:{self.attempt_number}:{uuid4().hex[:8]}"
        )
        self.operation_status = status
        now = monotonic()
        self.stage_started_at = now
        self.attempt_started_at = now
        self.operation_elapsed_seconds = 0.0
        self.attempt_elapsed_seconds = 0.0
        self.stage_elapsed_seconds = 0.0
        if operation_deadline_seconds is not None:
            self.operation_deadline_mono = now + operation_deadline_seconds
            self.attempt_deadline_mono = now + operation_deadline_seconds
        else:
            self.operation_deadline_mono = None
            self.attempt_deadline_mono = None
        self.clear_slow_warning()
        self.slow_warning_status = SlowWarningStatus.INACTIVE
        self._operation_open = True

        attempt = self._current_attempt_id()
        if attempt is not None:
            if status is OperationStatus.QUEUED:
                decision = self.ledger.register_queued(attempt)
            else:
                decision = self.ledger.register_started(attempt)
            if not decision.accepted:
                self.last_lifecycle_reject = decision.reason
                self._operation_open = False
                return False
            self.last_lifecycle_reject = None

        self.mark_real_progress()
        return True

    def queue_operation(self, operation: str) -> bool:
        return self.begin_operation(operation, status=OperationStatus.QUEUED)

    def terminal_operation(
        self,
        status: OperationStatus,
        *,
        reason_code: str | None = None,
        safe_message: str | None = None,
        allow_skip_without_start: bool = False,
    ) -> bool:
        """Apply a terminal status. Returns False if duplicate/invalid."""

        attempt = self._current_attempt_id()
        if attempt is not None:
            decision = self.ledger.register_terminal(
                attempt,
                status.value,
                allow_skip_without_start=allow_skip_without_start,
            )
            if not decision.accepted:
                self.last_lifecycle_reject = decision.reason
                return False
            self.last_lifecycle_reject = None

        self.operation_status = status
        if reason_code:
            self.reason_code = reason_code
        if safe_message:
            self.safe_message = safe_message
        self._operation_open = False
        self.clear_slow_warning()
        self.mark_real_progress()
        self._append_history()
        return True

    def complete_open_operation(self, status: OperationStatus = OperationStatus.COMPLETED) -> bool:
        """Close the current operation if still open. Returns True when a terminal was emitted."""

        if not self._operation_open:
            return False
        if self.operation_status in _TERMINAL_STATUSES:
            self._operation_open = False
            return False
        return self.terminal_operation(status)

    def _append_history(self) -> None:
        if len(self.history) >= 64:
            self.history.pop(0)
        self.history.append(
            {
                "operation": self.operation,
                "operation_id": self.operation_id,
                "status": self.operation_status.value,
                "overall_percent": round(self.overall_percent, 1),
                "major_phase": self.major_phase.value,
                "major_phase_percent": round(self.major_phase_percent, 1),
                "document_page_number": self.document_page_number,
                "selected_page_index": self.selected_page_index,
                "selected_pages_total": self.selected_pages_total,
                "page_number": self.document_page_number,
                "page_percent": self.page_percent,
                "reason_code": self.reason_code,
                "worker_generation": self.worker_generation,
                "attempt_number": self.attempt_number,
                "document_elapsed_seconds": round(self.document_elapsed_seconds, 1),
                "page_elapsed_seconds": (
                    round(self.page_elapsed_seconds, 1)
                    if self.page_elapsed_seconds is not None
                    else None
                ),
                "operation_elapsed_seconds": round(self.operation_elapsed_seconds, 1),
                "elapsed_seconds": round(self.elapsed_seconds, 1),
                "document_deadline_remaining_seconds": self.document_deadline_remaining_seconds,
                "page_deadline_remaining_seconds": self.page_deadline_remaining_seconds,
                "operation_deadline_remaining_seconds": self.operation_deadline_remaining_seconds,
                "deadline_remaining_seconds": self.deadline_remaining_seconds,
            }
        )

    def set_visual_selection_complete(self, *, pages_selected: int) -> None:
        self.major_phase = MajorPhase.VISUAL_OCR
        self.pages_selected = pages_selected
        self.selected_pages_total = pages_selected
        self.visual_pages_total = pages_selected
        self.pages_total = pages_selected
        self.bump_overall(OVERALL_VISUAL_SELECT_END)
        self.mark_real_progress()

    def set_visual_visibility_complete(self) -> None:
        self.major_phase = MajorPhase.VISUAL_OCR
        self.bump_overall(OVERALL_VISIBILITY_END)
        self.mark_real_progress()

    def set_visual_page_progress(
        self,
        *,
        pages_completed: int,
        pages_selected: int,
        page_number: int | None,
        page_percent: float,
        include_page_in_fraction: bool = True,
        selected_page_index: int | None = None,
        document_pages_total: int | None = None,
    ) -> None:
        """Map visual page progress into overall 41-63 band via selected-page fraction.

        ``page_number`` is the absolute document page. ``selected_page_index`` is
        the 1-based index within the selected visual workload.
        """

        total = max(pages_selected, 1)
        clamped_page = max(0.0, min(100.0, page_percent))
        contrib = (clamped_page / 100.0) if include_page_in_fraction else 0.0
        fraction = (pages_completed + contrib) / total
        overall = OVERALL_PAGE_PROCESSING_START + fraction * OVERALL_PAGE_PROCESSING_WIDTH
        overall = min(OVERALL_PAGE_PROCESSING_END, max(OVERALL_PAGE_PROCESSING_START, overall))
        self.major_phase = MajorPhase.VISUAL_OCR
        self.bump_overall(overall)
        self.pages_completed = pages_completed
        self.pages_selected = pages_selected
        self.selected_pages_total = pages_selected
        self.visual_pages_total = pages_selected
        self.pages_total = pages_selected
        if page_number is not None:
            self.document_page_number = page_number
            self.page_number = page_number
        if selected_page_index is not None:
            self.selected_page_index = selected_page_index
            self.visual_page_index = selected_page_index
        if document_pages_total is not None:
            self.document_pages_total = document_pages_total
        self.page_percent = clamped_page
        self.mark_real_progress()

    def set_native_only_progress(
        self,
        *,
        pages_completed: int,
        pages_total: int,
        document_page_number: int | None = None,
    ) -> None:
        """Advance overall for a native-only document without simulating OCR stages."""

        total = max(pages_total, 1)
        fraction = min(1.0, pages_completed / total)
        # Native-only: native policy end → summary start without visual OCR band work.
        overall = OVERALL_NATIVE_POLICY_END + fraction * (
            OVERALL_SUMMARY_START - OVERALL_NATIVE_POLICY_END
        )
        self.major_phase = MajorPhase.NATIVE_TRUST
        self.document_pages_total = pages_total
        self.selected_pages_total = pages_total
        self.pages_completed = pages_completed
        if document_page_number is not None:
            self.document_page_number = document_page_number
            self.page_number = document_page_number
            self.selected_page_index = document_page_number
        self.bump_overall(overall)
        self.mark_real_progress()

    def set_visual_summary_progress(self) -> None:
        self.major_phase = MajorPhase.VISUAL_OCR
        self.bump_overall(OVERALL_SUMMARY_START)
        self.mark_real_progress()

    def set_visual_authority_progress(self) -> None:
        self.major_phase = MajorPhase.VISUAL_OCR
        self.bump_overall(OVERALL_SUMMARY_MID)
        self.mark_real_progress()

    def set_visual_complete(self) -> None:
        self.major_phase = MajorPhase.VISUAL_OCR
        self.bump_overall(OVERALL_CAP)
        self.page_percent = 100.0
        self.mark_real_progress()


# Page-level visual OCR milestones (within a single page).
PAGE_QUEUED = 5.0
PAGE_RENDERED = 20.0
PAGE_PREPROCESSED = 25.0
PAGE_OCR_PIPELINE_DONE = 70.0
PAGE_MAPPING_DONE = 85.0
PAGE_GROUPED = 95.0
PAGE_PUBLISHED = 100.0

# Legacy aliases — unused for combined pipeline; kept for import compatibility.
PAGE_DETECTION_DONE = 55.0
PAGE_RECOGNITION_DONE = 85.0

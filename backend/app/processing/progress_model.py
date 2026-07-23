"""Deterministic Phase 4 three-level progress (overall / phase / page).

Overall is capped at 65%. Progress is monotonic and never advanced by heartbeats.

Visual page processing maps into the 41-63 band via document-wide page_fraction.
Overall reaches 65 only after summary publication and authority reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic


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


# Overall map — stage end boundaries.
OVERALL_JOB_ADMISSION_END = 2.0
OVERALL_CANONICAL_STAGING_END = 5.0
OVERALL_CANONICAL_END = 15.0
OVERALL_NATIVE_STRUCT_END = 17.0
OVERALL_NATIVE_EXTRACT_END = 32.0
OVERALL_NATIVE_POLICY_END = 35.0
OVERALL_VISUAL_SELECT_END = 37.0
OVERALL_VISIBILITY_END = 41.0
OVERALL_PAGE_PROCESSING_START = 41.0
OVERALL_PAGE_PROCESSING_END = 63.0
OVERALL_PAGE_PROCESSING_WIDTH = 22.0  # 41 → 63
OVERALL_SUMMARY_START = 63.0
OVERALL_SUMMARY_MID = 64.0
OVERALL_CAP = 65.0

# Visual phase derives from overall relative to the 35-65 visual band.
OVERALL_VISUAL_BAND_START = 35.0
OVERALL_VISUAL_BAND_WIDTH = 30.0

# Deprecated aliases kept for import compatibility.
OVERALL_VISUAL_BAND_START_LEGACY = OVERALL_VISUAL_BAND_START
OVERALL_VISUAL_BAND_WIDTH_LEGACY = OVERALL_VISUAL_BAND_WIDTH


@dataclass
class ProgressSnapshot:
    overall_percent: float = 0.0
    major_phase: MajorPhase = MajorPhase.ADMISSION
    major_phase_percent: float = 0.0
    page_number: int | None = None
    pages_total: int | None = None
    pages_completed: int = 0
    pages_selected: int = 0
    page_percent: float | None = None
    operation: str = "job_admission"
    operation_status: OperationStatus = OperationStatus.QUEUED
    progress_kind: ProgressKind = ProgressKind.DETERMINATE
    elapsed_seconds: float = 0.0
    document_elapsed_seconds: float = 0.0
    page_elapsed_seconds: float | None = None
    operation_elapsed_seconds: float = 0.0
    stage_elapsed_seconds: float = 0.0
    deadline_remaining_seconds: float | None = None
    worker_pid: int | None = None
    worker_generation: int | None = None
    worker_restart_count: int = 0
    attempt_number: int = 1
    max_attempts: int = 2
    last_real_progress_at: float = field(default_factory=monotonic)
    last_heartbeat_at: float | None = None
    reason_code: str | None = None
    safe_message: str | None = None
    job_started_at: float = field(default_factory=monotonic)
    stage_started_at: float = field(default_factory=monotonic)
    page_started_at: float | None = None
    history: list[dict[str, object]] = field(default_factory=list)
    _operation_open: bool = False

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
        self.document_elapsed_seconds = instant - self.job_started_at
        self.elapsed_seconds = self.document_elapsed_seconds
        self.operation_elapsed_seconds = instant - self.stage_started_at
        self.stage_elapsed_seconds = self.operation_elapsed_seconds
        if self.page_started_at is not None:
            self.page_elapsed_seconds = instant - self.page_started_at
        else:
            self.page_elapsed_seconds = None

    def mark_real_progress(self) -> None:
        now = monotonic()
        self.last_real_progress_at = now
        self._refresh_elapsed(now=now)

    def mark_heartbeat(self) -> None:
        now = monotonic()
        self.last_heartbeat_at = now
        self._refresh_elapsed(now=now)

    def begin_page(self, page_number: int) -> None:
        self.page_number = page_number
        self.page_started_at = monotonic()
        self.page_elapsed_seconds = 0.0

    def begin_operation(
        self, operation: str, *, status: OperationStatus = OperationStatus.STARTED
    ) -> None:
        self.operation = operation
        self.operation_status = status
        self.stage_started_at = monotonic()
        self.operation_elapsed_seconds = 0.0
        self.stage_elapsed_seconds = 0.0
        self._operation_open = True
        self.mark_real_progress()

    def terminal_operation(
        self,
        status: OperationStatus,
        *,
        reason_code: str | None = None,
        safe_message: str | None = None,
    ) -> None:
        self.operation_status = status
        if reason_code:
            self.reason_code = reason_code
        if safe_message:
            self.safe_message = safe_message
        self._operation_open = False
        self.mark_real_progress()
        self._append_history()

    def complete_open_operation(self, status: OperationStatus = OperationStatus.COMPLETED) -> bool:
        """Close the current operation if still open. Returns True when a terminal was emitted."""

        if not self._operation_open:
            return False
        if self.operation_status in {
            OperationStatus.COMPLETED,
            OperationStatus.FAILED,
            OperationStatus.TIMED_OUT,
            OperationStatus.CANCELLED,
            OperationStatus.SKIPPED,
        }:
            self._operation_open = False
            return False
        self.terminal_operation(status)
        return True

    def _append_history(self) -> None:
        if len(self.history) >= 64:
            self.history.pop(0)
        self.history.append(
            {
                "operation": self.operation,
                "status": self.operation_status.value,
                "overall_percent": round(self.overall_percent, 1),
                "major_phase": self.major_phase.value,
                "major_phase_percent": round(self.major_phase_percent, 1),
                "page_number": self.page_number,
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
                "deadline_remaining_seconds": self.deadline_remaining_seconds,
            }
        )

    def set_visual_selection_complete(self, *, pages_selected: int) -> None:
        self.major_phase = MajorPhase.VISUAL_OCR
        self.pages_selected = pages_selected
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
    ) -> None:
        """Map visual page progress into overall 41-63 band via document-wide fraction.

        ``page_fraction = (completed + current_page_percent/100) / total`` when
        ``include_page_in_fraction`` is True. After a page is fully finished, pass
        ``pages_completed=N`` with ``include_page_in_fraction=False`` (or
        ``page_percent=0``) so the finished page is not double-counted.
        Never pass ``pages_completed=N`` together with ``page_percent=100`` and
        ``include_page_in_fraction=True``.
        """

        total = max(pages_selected, 1)
        clamped_page = max(0.0, min(100.0, page_percent))
        contrib = (clamped_page / 100.0) if include_page_in_fraction else 0.0
        fraction = (pages_completed + contrib) / total
        overall = OVERALL_PAGE_PROCESSING_START + fraction * OVERALL_PAGE_PROCESSING_WIDTH
        # Page processing must not enter the summary band (63+) or the Phase 4 cap.
        overall = min(OVERALL_PAGE_PROCESSING_END, max(OVERALL_PAGE_PROCESSING_START, overall))
        self.major_phase = MajorPhase.VISUAL_OCR
        self.bump_overall(overall)
        self.pages_completed = pages_completed
        self.pages_selected = pages_selected
        self.pages_total = pages_selected
        self.page_number = page_number
        self.page_percent = clamped_page
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

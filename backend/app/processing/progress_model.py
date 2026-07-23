"""Deterministic Phase 4 three-level progress (overall / phase / page).

Overall is capped at 65%. Progress is monotonic and never advanced by heartbeats.
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


# Overall map (prompt §8) - stage end boundaries.
OVERALL_JOB_ADMISSION_END = 2.0
OVERALL_CANONICAL_STAGING_END = 5.0
OVERALL_CANONICAL_END = 15.0
OVERALL_NATIVE_STRUCT_END = 17.0
OVERALL_NATIVE_EXTRACT_END = 32.0
OVERALL_NATIVE_POLICY_END = 35.0
OVERALL_VISUAL_SELECT_END = 37.0
OVERALL_VISIBILITY_END = 41.0
OVERALL_VISUAL_BAND_START = 35.0
OVERALL_VISUAL_BAND_WIDTH = 30.0
OVERALL_CAP = 65.0


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
    history: list[dict[str, object]] = field(default_factory=list)

    def bump_overall(self, target: float) -> None:
        self.overall_percent = min(OVERALL_CAP, max(self.overall_percent, target))

    def mark_real_progress(self) -> None:
        now = monotonic()
        self.last_real_progress_at = now
        self.elapsed_seconds = now - self.job_started_at
        self.stage_elapsed_seconds = now - self.stage_started_at

    def mark_heartbeat(self) -> None:
        now = monotonic()
        self.last_heartbeat_at = now
        self.elapsed_seconds = now - self.job_started_at
        self.stage_elapsed_seconds = now - self.stage_started_at

    def begin_operation(
        self, operation: str, *, status: OperationStatus = OperationStatus.STARTED
    ) -> None:
        self.operation = operation
        self.operation_status = status
        self.stage_started_at = monotonic()
        self.stage_elapsed_seconds = 0.0
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
        self.mark_real_progress()
        self._append_history()

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
                "elapsed_seconds": round(self.elapsed_seconds, 1),
            }
        )

    def set_visual_page_progress(
        self,
        *,
        pages_completed: int,
        pages_selected: int,
        page_number: int | None,
        page_percent: float,
    ) -> None:
        """Map visual page progress into overall 35-65 band (prompt §9)."""

        total = max(pages_selected, 1)
        fraction = (pages_completed + max(0.0, min(page_percent, 100.0)) / 100.0) / total
        overall = OVERALL_VISUAL_BAND_START + fraction * OVERALL_VISUAL_BAND_WIDTH
        self.bump_overall(overall)
        self.pages_completed = pages_completed
        self.pages_selected = pages_selected
        self.pages_total = pages_selected
        self.page_number = page_number
        self.page_percent = max(0.0, min(100.0, page_percent))
        self.major_phase = MajorPhase.VISUAL_OCR
        self.major_phase_percent = min(100.0, fraction * 100.0)
        self.mark_real_progress()


# Page-level visual OCR map (prompt §9).
PAGE_QUEUED = 5.0
PAGE_RENDERED = 20.0
PAGE_PREPROCESSED = 25.0
PAGE_DETECTION_DONE = 55.0
PAGE_RECOGNITION_DONE = 85.0
PAGE_GROUPED = 95.0
PAGE_PUBLISHED = 100.0

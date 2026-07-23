"""Privacy-safe progress / stage logging with visible development fields."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("veridemand.progress")


def log_progress(
    event: str,
    *,
    level: int = logging.INFO,
    document_id: str | None = None,
    job_id: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    overall_percent: float | None = None,
    major_phase: str | None = None,
    major_phase_percent: float | None = None,
    page_number: int | None = None,
    pages_total: int | None = None,
    pages_completed: int | None = None,
    page_percent: float | None = None,
    operation: str | None = None,
    operation_status: str | None = None,
    progress_kind: str | None = None,
    elapsed_seconds: float | None = None,
    stage_elapsed_seconds: float | None = None,
    deadline_remaining_seconds: float | None = None,
    worker_pid: int | None = None,
    worker_generation: int | None = None,
    worker_restart_count: int | None = None,
    attempt_number: int | None = None,
    max_attempts: int | None = None,
    reason_code: str | None = None,
    **extra: Any,
) -> None:
    """Emit one structured progress line (never OCR/native text)."""

    payload: dict[str, Any] = {
        "event": event,
        "operation": operation,
        "operation_status": operation_status,
        "document_id": document_id,
        "job_id": job_id,
        "session_id": session_id,
        "request_id": request_id,
        "overall_percent": None if overall_percent is None else round(overall_percent, 1),
        "major_phase": major_phase,
        "major_phase_percent": None
        if major_phase_percent is None
        else round(major_phase_percent, 1),
        "page_number": page_number,
        "pages_total": pages_total,
        "pages_completed": pages_completed,
        "page_percent": None if page_percent is None else round(page_percent, 1),
        "progress_kind": progress_kind,
        "elapsed_seconds": None if elapsed_seconds is None else round(elapsed_seconds, 1),
        "stage_elapsed_seconds": None
        if stage_elapsed_seconds is None
        else round(stage_elapsed_seconds, 1),
        "deadline_remaining_seconds": None
        if deadline_remaining_seconds is None
        else round(deadline_remaining_seconds, 1),
        "worker_pid": worker_pid,
        "worker_generation": worker_generation,
        "worker_restart_count": worker_restart_count,
        "attempt_number": attempt_number,
        "max_attempts": max_attempts,
        "reason_code": reason_code,
        "monotonic_s": round(time.monotonic(), 3),
    }
    for key, value in extra.items():
        if value is not None and key not in payload:
            payload[key] = value
    # Message is the event name so the formatter line starts with a clear verb.
    logger.log(level, event, extra={k: v for k, v in payload.items() if v is not None})


def log_stage(
    *,
    component: str,
    operation: str,
    document_id: str | None = None,
    job_id: str | None = None,
    page_number: int | None = None,
    elapsed_s: float | None = None,
    worker_pid: int | None = None,
    **extra: Any,
) -> None:
    """Backward-compatible stage helper — routes to ``log_progress``."""

    log_progress(
        "visual_progress" if component == "visual" else f"{component}_progress",
        document_id=document_id,
        job_id=job_id,
        page_number=page_number,
        operation=operation,
        operation_status=str(extra.pop("status", "running")),
        elapsed_seconds=elapsed_s,
        worker_pid=worker_pid,
        component=component,
        **extra,
    )

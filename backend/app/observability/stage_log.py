"""Privacy-safe processing stage timestamps for diagnosis (no document text)."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("veridemand.stage")


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
    """Emit a structured stage log without OCR/native text payloads."""

    payload: dict[str, Any] = {
        "component": component,
        "operation": operation,
        "monotonic_s": round(time.monotonic(), 3),
    }
    if document_id is not None:
        payload["document_id"] = document_id
    if job_id is not None:
        payload["job_id"] = job_id
    if page_number is not None:
        payload["page_number"] = page_number
    if elapsed_s is not None:
        payload["elapsed_s"] = round(elapsed_s, 3)
    if worker_pid is not None:
        payload["worker_pid"] = worker_pid
    for key, value in extra.items():
        if value is not None:
            payload[key] = value
    logger.info("processing_stage", extra=payload)

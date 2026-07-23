"""Development logging with visibly rendered structured fields.

``logging.basicConfig`` alone prints only the message string, which hid
``extra=`` payloads as generic ``processing_stage`` lines. This formatter
renders privacy-safe key/value fields on every VeriDemand log line.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

_SAFE_KEYS = (
    "event",
    "component",
    "operation",
    "operation_status",
    "status",
    "document_id",
    "job_id",
    "session_id",
    "request_id",
    "overall_percent",
    "major_phase",
    "major_phase_percent",
    "page_number",
    "pages_total",
    "pages_completed",
    "page_percent",
    "progress_kind",
    "elapsed_seconds",
    "stage_elapsed_seconds",
    "deadline_remaining_seconds",
    "worker_pid",
    "worker_generation",
    "worker_restart_count",
    "attempt_number",
    "max_attempts",
    "reason_code",
    "restart_reason",
    "active_request_action",
    "previous_pid",
    "previous_generation",
    "new_pid",
    "new_generation",
    "percent",
    "pid",
    "gen",
    "rss_mb",
    "last_real_progress_age",
    "requested_dpi",
    "effective_dpi",
    "render_source_policy",
    "downscale_reason",
    "source_resolution_cap_applied",
    "source_width_px",
    "source_height_px",
    "canonical_width_points",
    "canonical_height_points",
    "width_pixels",
    "height_pixels",
    "rendered_pixel_count",
    "detector_limit_side_len",
    "detector_input_width",
    "detector_input_height",
    "render_duration_seconds",
    "preprocess_duration_seconds",
    "detection_duration_seconds",
    "detected_line_count",
    "peak_rss_mb",
)


class DevProgressFormatter(logging.Formatter):
    """UTC ISO-8601 ms + level + message + selected extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        parts = [f"{ts} {record.levelname} {record.getMessage()}"]
        for key in _SAFE_KEYS:
            if hasattr(record, key):
                value = getattr(record, key)
                if value is None or value == "":
                    continue
                parts.append(f"{key}={value}")
        return " ".join(parts)


def configure_dev_logging(level: str | int = "INFO") -> None:
    """Install the development formatter on the root logger (idempotent)."""

    root = logging.getLogger()
    resolved = (
        level if isinstance(level, int) else getattr(logging, str(level).upper(), logging.INFO)
    )
    root.setLevel(resolved)
    formatter = DevProgressFormatter()
    if root.handlers:
        for handler in root.handlers:
            handler.setFormatter(formatter)
            handler.setLevel(resolved)
        return
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.setLevel(resolved)
    root.addHandler(handler)

"""Structured logging with sensitive-value masking."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

SENSITIVE_KEY_RE = re.compile(
    r"(password|secret|token|api[_-]?key|authorization|cookie|ssn|dob|"
    r"medical|diagnosis|document_text|page_text)",
    re.IGNORECASE,
)
MASK = "***"


def mask_value(key: str, value: Any) -> Any:
    if SENSITIVE_KEY_RE.search(key):
        return MASK
    if isinstance(value, dict):
        return {k: mask_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_value(key, item) for item in value]
    return value


def mask_mapping(data: dict[str, Any]) -> dict[str, Any]:
    return {k: mask_value(k, v) for k, v in data.items()}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id is not None:
            payload["request_id"] = request_id
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(mask_mapping(extra))
        # Mask common sensitive attributes if attached directly
        for attr in ("password", "secret", "api_key", "document_text", "medical_text"):
            if hasattr(record, attr):
                payload[attr] = MASK
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

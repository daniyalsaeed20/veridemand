"""Logging mask tests."""

from __future__ import annotations

import json
import logging

from app.core.logging import JsonFormatter, mask_mapping


def test_mask_mapping_redacts_sensitive_keys() -> None:
    masked = mask_mapping(
        {
            "api_key": "SUPER_SECRET_VALUE_XYZ",
            "password": "hunter2",
            "document_text": "patient diagnosis text",
            "safe": "ok",
        }
    )
    assert masked["api_key"] == "***"
    assert masked["password"] == "***"
    assert masked["document_text"] == "***"
    assert masked["safe"] == "ok"
    assert "SUPER_SECRET_VALUE_XYZ" not in json.dumps(masked)


def test_json_formatter_masks_record_attrs() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.api_key = "SUPER_SECRET_VALUE_XYZ"  # type: ignore[attr-defined]
    record.extra_fields = {"password": "hunter2", "request_id": "req_test"}
    out = formatter.format(record)
    assert "SUPER_SECRET_VALUE_XYZ" not in out
    assert "hunter2" not in out
    assert "***" in out

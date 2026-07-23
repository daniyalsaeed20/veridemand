"""Progress model and development log formatter tests."""

from __future__ import annotations

import logging

import pytest

from backend.app.observability.dev_logging import DevProgressFormatter, configure_dev_logging
from backend.app.observability.stage_log import log_progress
from backend.app.processing.progress_model import OVERALL_CAP, ProgressSnapshot


def test_overall_progress_is_monotonic_and_capped() -> None:
    snap = ProgressSnapshot()
    snap.bump_overall(20)
    snap.bump_overall(10)
    assert snap.overall_percent == 20
    snap.bump_overall(90)
    assert snap.overall_percent == OVERALL_CAP


def test_heartbeat_does_not_advance_percent() -> None:
    snap = ProgressSnapshot()
    snap.set_visual_page_progress(
        pages_completed=0, pages_selected=2, page_number=1, page_percent=25
    )
    before = snap.overall_percent
    snap.mark_heartbeat()
    assert snap.overall_percent == before


def test_dev_formatter_renders_fields() -> None:
    configure_dev_logging("INFO")
    record = logging.LogRecord(
        name="veridemand.progress",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="visual_progress",
        args=(),
        exc_info=None,
    )
    record.overall_percent = 48.0
    record.operation = "paddle_text_detection"
    record.document_id = "doc_abc"
    formatted = DevProgressFormatter().format(record)
    assert "visual_progress" in formatted
    assert "overall_percent=48.0" in formatted
    assert "operation=paddle_text_detection" in formatted
    assert "processing_stage" not in formatted


def test_log_progress_message_is_event_name(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="veridemand.progress"):
        log_progress(
            "visual_progress",
            document_id="doc_x",
            operation="visual_page_render",
            operation_status="started",
            overall_percent=41.0,
        )
    assert any("visual_progress" in r.getMessage() for r in caplog.records)

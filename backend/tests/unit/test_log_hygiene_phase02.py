"""Ensure operational logs do not contain document text body by default."""

from __future__ import annotations

import logging
from pathlib import Path

from tests.fixtures.upload_builders import write_minimal_pdf
from tests.helpers_process import make_client, upload_and_process


def test_process_logs_exclude_document_text(
    tmp_path: Path, caplog: logging.LogCaptureFixture
) -> None:
    pdf = tmp_path / "a.pdf"
    write_minimal_pdf(pdf)
    with make_client(tmp_path / "w", log_document_text=False) as client:
        with caplog.at_level(logging.INFO):
            upload_and_process(
                client,
                [("a.pdf", pdf.read_bytes(), "application/pdf")],
            )
        joined = " ".join(r.getMessage() for r in caplog.records)
        assert "%PDF" not in joined
        assert "BT /F1" not in joined
        assert "Hello" not in joined
        assert "World" not in joined

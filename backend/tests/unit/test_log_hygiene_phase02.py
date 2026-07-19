"""Ensure operational logs do not contain document text body by default."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.server_settings import ServerSettings
from app.main import create_app
from app.models.app_settings import AppSettings
from app.models.case_session import CaseSession
from app.services.documents.convert_docx import fake_docx_converter_success
from tests.fixtures.upload_builders import write_minimal_pdf


def test_process_logs_exclude_document_text(
    tmp_path: Path, caplog: logging.LogCaptureFixture
) -> None:
    settings = AppSettings(log_document_text=False)
    app = create_app(
        app_settings=settings,
        server_settings=ServerSettings(
            cors_origins=["http://localhost:5173"],
            log_level="INFO",
            app_version="0.0.0-dev",
            temp_root=tmp_path / "sessions",
            max_active_sessions=32,
            session_cleanup_interval_seconds=3600,
        ),
    )
    pdf = tmp_path / "a.pdf"
    write_minimal_pdf(pdf)
    with TestClient(app) as client:
        client.app.state.process_service.set_docx_converter(fake_docx_converter_success)
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        with caplog.at_level(logging.INFO):
            client.post(
                f"/api/v1/sessions/{session.id}/documents",
                files=[("files", ("a.pdf", pdf.read_bytes(), "application/pdf"))],
            )
            client.post(f"/api/v1/sessions/{session.id}/process")
        joined = " ".join(r.getMessage() for r in caplog.records)
        assert "%PDF" not in joined
        assert "BT /F1" not in joined

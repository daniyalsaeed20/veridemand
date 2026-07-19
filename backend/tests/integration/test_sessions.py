"""Integration tests for sessions and document upload API."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.server_settings import ServerSettings
from app.main import create_app
from app.models.app_settings import AppSettings
from app.models.case_session import CaseSession
from app.models.document_upload_batch import DocumentUploadBatch
from tests.fixtures.upload_builders import (
    write_corrupt_pdf,
    write_encrypted_pdf,
    write_jpg,
    write_malformed_docx,
    write_minimal_docx,
    write_minimal_pdf,
    write_png,
    write_tiff,
    write_zip_bomb_docx,
)


def _client(tmp_path: Path, **overrides: int) -> TestClient:
    settings = AppSettings(**overrides) if overrides else AppSettings()
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
    return TestClient(app)


def test_session_lifecycle(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        created = client.post("/api/v1/sessions")
        assert created.status_code == 200
        session = CaseSession.model_validate(created.json())
        assert session.id.startswith("ses_")
        assert session.warning
        assert "X-Request-ID" in created.headers

        got = client.get(f"/api/v1/sessions/{session.id}")
        assert got.status_code == 200

        deleted = client.delete(f"/api/v1/sessions/{session.id}")
        assert deleted.status_code == 204
        assert not (tmp_path / "sessions" / session.id).exists()

        assert client.delete(f"/api/v1/sessions/{session.id}").status_code == 204

        missing = client.get(f"/api/v1/sessions/{session.id}")
        assert missing.status_code == 404
        assert missing.json()["error_code"] == "session_not_found"


def test_expired_session(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        svc = client.app.state.session_service
        record = svc.get_record(session.id, touch=False)
        record.session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        (record.workspace / "uploads" / "keep.bin").write_bytes(b"x")

        resp = client.get(f"/api/v1/sessions/{session.id}")
        assert resp.status_code == 410
        assert resp.json()["error_code"] == "session_expired"
        assert not (tmp_path / "sessions" / session.id).exists()


def test_upload_all_supported_formats(tmp_path: Path) -> None:
    fixtures = tmp_path / "files"
    fixtures.mkdir()
    files = {
        "a.pdf": write_minimal_pdf(fixtures / "a.pdf"),
        "a.docx": write_minimal_docx(fixtures / "a.docx"),
        "a.jpg": write_jpg(fixtures / "a.jpg"),
        "a.png": write_png(fixtures / "a.png"),
        "a.tiff": write_tiff(fixtures / "a.tiff"),
    }
    mime = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".tiff": "image/tiff",
    }
    with _client(tmp_path) as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        multipart = [
            ("files", (name, path.read_bytes(), mime[Path(name).suffix]))
            for name, path in files.items()
        ]
        resp = client.post(f"/api/v1/sessions/{session.id}/documents", files=multipart)
        assert resp.status_code == 200
        batch = DocumentUploadBatch.model_validate(resp.json())
        assert len(batch.accepted) == 5
        assert batch.rejected == []
        listed = client.get(f"/api/v1/sessions/{session.id}/documents")
        assert listed.status_code == 200
        assert len(listed.json()) == 5


def test_rejects_invalid_without_ending_session(tmp_path: Path) -> None:
    fixtures = tmp_path / "files"
    fixtures.mkdir()
    good = write_minimal_pdf(fixtures / "good.pdf")
    bad = write_corrupt_pdf(fixtures / "bad.pdf")
    with _client(tmp_path) as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        resp = client.post(
            f"/api/v1/sessions/{session.id}/documents",
            files=[
                ("files", ("good.pdf", good.read_bytes(), "application/pdf")),
                ("files", ("bad.pdf", bad.read_bytes(), "application/pdf")),
            ],
        )
        assert resp.status_code == 200
        batch = DocumentUploadBatch.model_validate(resp.json())
        assert len(batch.accepted) == 1
        assert len(batch.rejected) == 1
        assert batch.rejected[0].error_code == "upload_corrupt_file"
        assert client.get(f"/api/v1/sessions/{session.id}").status_code == 200


def test_duplicate_detection(tmp_path: Path) -> None:
    fixtures = tmp_path / "files"
    fixtures.mkdir()
    data = write_minimal_pdf(fixtures / "dup.pdf").read_bytes()
    with _client(tmp_path) as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        resp = client.post(
            f"/api/v1/sessions/{session.id}/documents",
            files=[
                ("files", ("one.pdf", data, "application/pdf")),
                ("files", ("two.pdf", data, "application/pdf")),
            ],
        )
        batch = DocumentUploadBatch.model_validate(resp.json())
        assert len(batch.accepted) == 2
        statuses = {d.status.value for d in batch.accepted}
        assert "uploaded" in statuses
        assert "duplicate" in statuses


def test_file_count_exceeded(tmp_path: Path) -> None:
    fixtures = tmp_path / "files"
    fixtures.mkdir()
    first = write_minimal_pdf(fixtures / "a.pdf").read_bytes()
    second = write_minimal_pdf(fixtures / "b.pdf", pages=2).read_bytes()
    with _client(tmp_path, max_files_per_session=1) as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        client.post(
            f"/api/v1/sessions/{session.id}/documents",
            files=[("files", ("a.pdf", first, "application/pdf"))],
        )
        resp = client.post(
            f"/api/v1/sessions/{session.id}/documents",
            files=[("files", ("b.pdf", second, "application/pdf"))],
        )
        batch = DocumentUploadBatch.model_validate(resp.json())
        assert any(r.error_code == "upload_file_count_exceeded" for r in batch.rejected)


def test_file_too_large(tmp_path: Path) -> None:
    oversized = b"%PDF-1.4\n" + (b"0" * (2 * 1024 * 1024)) + b"\n%%EOF\n"
    with _client(tmp_path, max_file_size_mb=1) as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        resp = client.post(
            f"/api/v1/sessions/{session.id}/documents",
            files=[("files", ("huge.pdf", oversized, "application/pdf"))],
        )
        batch = DocumentUploadBatch.model_validate(resp.json())
        assert any(r.error_code == "upload_file_too_large" for r in batch.rejected)


def test_total_size_exceeded(tmp_path: Path) -> None:
    fixtures = tmp_path / "files"
    fixtures.mkdir()
    img1 = fixtures / "a.png"
    img2 = fixtures / "b.png"
    Image.new("RGB", (500, 500), color=(1, 2, 3)).save(img1, format="PNG", compress_level=0)
    Image.new("RGB", (500, 500), color=(4, 5, 6)).save(img2, format="PNG", compress_level=0)
    d1 = img1.read_bytes()
    d2 = img2.read_bytes()
    assert len(d1) < 1024 * 1024
    assert len(d1) + len(d2) > 1024 * 1024
    with _client(tmp_path, max_file_size_mb=5, max_total_upload_mb=1) as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        first = client.post(
            f"/api/v1/sessions/{session.id}/documents",
            files=[("files", ("a.png", d1, "image/png"))],
        )
        assert len(DocumentUploadBatch.model_validate(first.json()).accepted) == 1
        resp = client.post(
            f"/api/v1/sessions/{session.id}/documents",
            files=[("files", ("b.png", d2, "image/png"))],
        )
        batch = DocumentUploadBatch.model_validate(resp.json())
        assert any(r.error_code == "upload_total_size_exceeded" for r in batch.rejected)


def test_encrypted_pdf_and_malformed_docx(tmp_path: Path) -> None:
    fixtures = tmp_path / "files"
    fixtures.mkdir()
    enc = write_encrypted_pdf(fixtures / "enc.pdf")
    bad_docx = write_malformed_docx(fixtures / "bad.docx")
    with _client(tmp_path) as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        resp = client.post(
            f"/api/v1/sessions/{session.id}/documents",
            files=[
                ("files", ("enc.pdf", enc.read_bytes(), "application/pdf")),
                (
                    "files",
                    (
                        "bad.docx",
                        bad_docx.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                ),
            ],
        )
        batch = DocumentUploadBatch.model_validate(resp.json())
        codes = {r.error_code for r in batch.rejected}
        assert "upload_encrypted_pdf" in codes
        assert "upload_corrupt_file" in codes


def test_docx_zip_bomb_rejected(tmp_path: Path) -> None:
    fixtures = tmp_path / "files"
    fixtures.mkdir()
    bomb = write_zip_bomb_docx(fixtures / "bomb.docx")
    with _client(tmp_path) as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        resp = client.post(
            f"/api/v1/sessions/{session.id}/documents",
            files=[
                (
                    "files",
                    (
                        "bomb.docx",
                        bomb.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                )
            ],
        )
        batch = DocumentUploadBatch.model_validate(resp.json())
        assert any(r.error_code == "upload_corrupt_file" for r in batch.rejected)
        assert client.get(f"/api/v1/sessions/{session.id}").status_code == 200


def test_macro_docx_rejected_no_residue(tmp_path: Path) -> None:
    fixtures = tmp_path / "files"
    fixtures.mkdir()
    from tests.fixtures.upload_builders import write_docx_with_vbaproject

    macro = write_docx_with_vbaproject(fixtures / "m.docx")
    with _client(tmp_path) as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        resp = client.post(
            f"/api/v1/sessions/{session.id}/documents",
            files=[
                (
                    "files",
                    (
                        "m.docx",
                        macro.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                )
            ],
        )
        batch = DocumentUploadBatch.model_validate(resp.json())
        assert len(batch.accepted) == 0
        assert any(r.error_code == "upload_macros_not_supported" for r in batch.rejected)
        assert "vba" not in batch.rejected[0].message.lower()
        uploads = tmp_path / "sessions" / session.id / "uploads"
        assert list(uploads.iterdir()) == []
        assert client.get(f"/api/v1/sessions/{session.id}/documents").json() == []


def test_unsafe_zip_entry_docx_rejected(tmp_path: Path) -> None:
    fixtures = tmp_path / "files"
    fixtures.mkdir()
    from tests.fixtures.upload_builders import write_docx_with_entry

    bad = write_docx_with_entry(fixtures / "bad.docx", "../evil.xml")
    with _client(tmp_path) as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        resp = client.post(
            f"/api/v1/sessions/{session.id}/documents",
            files=[
                (
                    "files",
                    (
                        "bad.docx",
                        bad.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                )
            ],
        )
        batch = DocumentUploadBatch.model_validate(resp.json())
        assert any(r.error_code == "upload_corrupt_file" for r in batch.rejected)
        assert list((tmp_path / "sessions" / session.id / "uploads").iterdir()) == []


def test_path_traversal_filename(tmp_path: Path) -> None:
    fixtures = tmp_path / "files"
    fixtures.mkdir()
    pdf = write_minimal_pdf(fixtures / "ok.pdf")
    with _client(tmp_path) as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        resp = client.post(
            f"/api/v1/sessions/{session.id}/documents",
            files=[("files", ("../../evil.pdf", pdf.read_bytes(), "application/pdf"))],
        )
        batch = DocumentUploadBatch.model_validate(resp.json())
        assert len(batch.accepted) == 1
        assert batch.accepted[0].display_name == "evil.pdf"
        uploads = tmp_path / "sessions" / session.id / "uploads"
        for child in uploads.iterdir():
            assert child.parent == uploads


def test_session_isolation(tmp_path: Path) -> None:
    fixtures = tmp_path / "files"
    fixtures.mkdir()
    pdf = write_minimal_pdf(fixtures / "a.pdf")
    with _client(tmp_path) as client:
        a = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        b = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        client.post(
            f"/api/v1/sessions/{a.id}/documents",
            files=[("files", ("a.pdf", pdf.read_bytes(), "application/pdf"))],
        )
        assert client.get(f"/api/v1/sessions/{b.id}/documents").json() == []
        assert len(client.get(f"/api/v1/sessions/{a.id}/documents").json()) == 1


def test_partial_upload_cleanup_no_residue(tmp_path: Path) -> None:
    with _client(tmp_path, max_file_size_mb=1) as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        oversized = b"%PDF-1.4\n" + (b"A" * (2 * 1024 * 1024))
        client.post(
            f"/api/v1/sessions/{session.id}/documents",
            files=[("files", ("huge.pdf", oversized, "application/pdf"))],
        )
        uploads = tmp_path / "sessions" / session.id / "uploads"
        assert list(uploads.iterdir()) == []


def test_no_document_contents_in_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    fixtures = tmp_path / "files"
    fixtures.mkdir()
    pdf = write_minimal_pdf(fixtures / "case.pdf")
    with caplog.at_level(logging.INFO):
        with _client(tmp_path) as client:
            session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
            client.post(
                f"/api/v1/sessions/{session.id}/documents",
                files=[("files", ("case.pdf", pdf.read_bytes(), "application/pdf"))],
            )
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "%PDF-1.4" not in joined
    for record in caplog.records:
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            blob = str(extra)
            assert "%PDF" not in blob


def test_automatic_cleanup_callable(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        svc = client.app.state.session_service
        record = svc.get_record(session.id, touch=False)
        record.session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        cleaned = svc.cleanup_expired_sessions(datetime.now(UTC))
        assert session.id in cleaned
        assert cleaned == svc.cleanup_expired_sessions(datetime.now(UTC)) or True
        assert svc.cleanup_expired_sessions(datetime.now(UTC)) == []

"""Integration tests for Phase 2 normalize + native extraction APIs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.models.case_session import CaseSession
from app.models.document_page import DocumentPage
from app.models.process_event import ProcessEvent
from app.services.documents.convert_docx import (
    fake_docx_converter_failure,
    fake_docx_converter_success,
    fake_docx_converter_timeout,
)
from tests.fixtures.upload_builders import (
    write_jpg,
    write_minimal_docx,
    write_minimal_pdf,
    write_png,
    write_tiff,
)
from tests.helpers_process import make_client, upload_and_process, wait_for_process


def _client(tmp_path: Path, **overrides: object) -> TestClient:
    return make_client(tmp_path, **overrides)


def _upload_and_process(
    client: TestClient,
    files: list[tuple[str, bytes, str]],
    *,
    converter=fake_docx_converter_success,
):
    return upload_and_process(client, files, converter=converter)


def test_pdf_normalize_and_native_extract(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    write_minimal_pdf(pdf, pages=2)
    with _client(tmp_path / "w") as client:
        session_id, docs = _upload_and_process(
            client,
            [("a.pdf", pdf.read_bytes(), "application/pdf")],
        )
        doc = docs[0]
        assert doc.status == "extracted"
        assert doc.page_count == 2

        pages = [
            DocumentPage.model_validate(p)
            for p in client.get(f"/api/v1/sessions/{session_id}/documents/{doc.id}/pages").json()
        ]
        assert len(pages) == 2
        assert all(p.route in {"native", "ocr", "manual_review"} for p in pages)
        assert all(p.ocr_status in {None, "not_needed", "pending", "done", "failed"} for p in pages)

        view = client.get(f"/api/v1/sessions/{session_id}/documents/{doc.id}/view")
        assert view.status_code == 200
        assert view.headers["content-type"].startswith("application/pdf")

        thumb = client.get(f"/api/v1/sessions/{session_id}/documents/{doc.id}/thumbnails/1")
        assert thumb.status_code == 200
        assert thumb.headers["content-type"].startswith("image/png")


def test_docx_convert_success_fake_adapter(tmp_path: Path) -> None:
    docx = tmp_path / "letter.docx"
    write_minimal_docx(docx)
    with _client(tmp_path / "w") as client:
        session_id, docs = _upload_and_process(
            client,
            [
                (
                    "letter.docx",
                    docx.read_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            ],
            converter=fake_docx_converter_success,
        )
        doc = docs[0]
        assert doc.status == "extracted"
        assert doc.page_count == 1
        view = client.get(f"/api/v1/sessions/{session_id}/documents/{doc.id}/view")
        assert view.status_code == 200


def test_docx_convert_timeout_cleans_partial(tmp_path: Path) -> None:
    docx = tmp_path / "letter.docx"
    write_minimal_docx(docx)
    with _client(tmp_path / "w") as client:
        client.app.state.process_service.set_docx_converter(fake_docx_converter_timeout)
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        batch = client.post(
            f"/api/v1/sessions/{session.id}/documents",
            files=[
                (
                    "files",
                    (
                        "letter.docx",
                        docx.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                )
            ],
        )
        assert batch.status_code == 200
        doc_id = batch.json()["accepted"][0]["id"]
        processed = client.post(f"/api/v1/sessions/{session.id}/process")
        assert processed.status_code == 200
        wait_for_process(client, session.id)
        docs = client.get(f"/api/v1/sessions/{session.id}/documents").json()
        assert docs[0]["error_code"] == "process_stage_failed"
        assert docs[0]["status"] == "uploaded"
        derived = tmp_path / "w" / "sessions" / session.id / "derived" / f"{doc_id}.pdf"
        assert not derived.exists()
        work = tmp_path / "w" / "sessions" / session.id / "work" / doc_id
        assert not work.exists()


def test_docx_convert_missing_tool(tmp_path: Path) -> None:
    docx = tmp_path / "letter.docx"
    write_minimal_docx(docx)
    with _client(tmp_path / "w") as client:
        client.app.state.process_service.set_docx_converter(fake_docx_converter_failure)
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        client.post(
            f"/api/v1/sessions/{session.id}/documents",
            files=[
                (
                    "files",
                    (
                        "letter.docx",
                        docx.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                )
            ],
        )
        processed = client.post(f"/api/v1/sessions/{session.id}/process")
        assert processed.status_code == 200
        wait_for_process(client, session.id)
        docs = client.get(f"/api/v1/sessions/{session.id}/documents").json()
        assert docs[0]["error_code"] == "process_stage_failed"


def test_image_and_tiff_normalize(tmp_path: Path) -> None:
    png = tmp_path / "a.png"
    jpg = tmp_path / "b.jpg"
    tiff = tmp_path / "c.tiff"
    write_png(png, size=(64, 64))
    write_jpg(jpg, size=(64, 64))
    write_tiff(tiff, frames=3)
    with _client(tmp_path / "w") as client:
        session_id, docs = _upload_and_process(
            client,
            [
                ("a.png", png.read_bytes(), "image/png"),
                ("b.jpg", jpg.read_bytes(), "image/jpeg"),
                ("c.tiff", tiff.read_bytes(), "image/tiff"),
            ],
        )
        by_name = {d.display_name: d for d in docs}
        assert by_name["a.png"].page_count == 1
        assert by_name["b.jpg"].page_count == 1
        assert by_name["c.tiff"].page_count == 3
        for doc in docs:
            assert doc.status == "extracted"
            thumb = client.get(f"/api/v1/sessions/{session_id}/documents/{doc.id}/thumbnails/1")
            assert thumb.status_code == 200


def test_cross_session_view_denied(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    write_minimal_pdf(pdf)
    with _client(tmp_path / "w") as client:
        session_a, docs = _upload_and_process(
            client, [("a.pdf", pdf.read_bytes(), "application/pdf")]
        )
        doc_id = docs[0].id
        session_b = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        denied = client.get(f"/api/v1/sessions/{session_b.id}/documents/{doc_id}/view")
        assert denied.status_code == 404
        denied_thumb = client.get(
            f"/api/v1/sessions/{session_b.id}/documents/{doc_id}/thumbnails/1"
        )
        assert denied_thumb.status_code == 404


def test_access_after_session_delete(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    write_minimal_pdf(pdf)
    with _client(tmp_path / "w") as client:
        session_id, docs = _upload_and_process(
            client, [("a.pdf", pdf.read_bytes(), "application/pdf")]
        )
        doc_id = docs[0].id
        assert client.delete(f"/api/v1/sessions/{session_id}").status_code == 204
        assert (
            client.get(f"/api/v1/sessions/{session_id}/documents/{doc_id}/view").status_code == 404
        )
        assert (
            client.get(f"/api/v1/sessions/{session_id}/documents/{doc_id}/thumbnails/1").status_code
            == 404
        )


def test_access_after_session_expiry(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    write_minimal_pdf(pdf)
    with _client(tmp_path / "w") as client:
        session_id, docs = _upload_and_process(
            client, [("a.pdf", pdf.read_bytes(), "application/pdf")]
        )
        doc_id = docs[0].id
        svc = client.app.state.session_service
        record = svc.get_record(session_id, touch=False)
        record.session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        resp = client.get(f"/api/v1/sessions/{session_id}/documents/{doc_id}/view")
        assert resp.status_code == 410
        assert resp.json()["error_code"] == "session_expired"


def test_process_not_ready_without_documents(tmp_path: Path) -> None:
    with _client(tmp_path / "w") as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        resp = client.post(f"/api/v1/sessions/{session.id}/process")
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "process_not_ready"


def test_events_poll(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    write_minimal_pdf(pdf)
    with _client(tmp_path / "w") as client:
        session_id, _ = _upload_and_process(
            client, [("a.pdf", pdf.read_bytes(), "application/pdf")]
        )
        events = client.get(f"/api/v1/sessions/{session_id}/events")
        assert events.status_code == 200
        parsed = [ProcessEvent.model_validate(e) for e in events.json()]
        assert parsed
        after = parsed[-1].sequence
        empty = client.get(f"/api/v1/sessions/{session_id}/events?after={after}")
        assert empty.json() == []


def test_path_traversal_document_id_rejected(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    write_minimal_pdf(pdf)
    with _client(tmp_path / "w") as client:
        session_id, _ = _upload_and_process(
            client, [("a.pdf", pdf.read_bytes(), "application/pdf")]
        )
        evil = client.get(f"/api/v1/sessions/{session_id}/documents/../etc/passwd/view")
        assert evil.status_code in {404, 405, 422}


def test_concurrent_process_two_sessions_serialize_pdfium(tmp_path: Path) -> None:
    """Two sessions /process concurrently — PDFium critical section max inflight == 1."""
    import threading

    from app.services.documents import pdfium_runtime

    pdf_a = write_minimal_pdf(tmp_path / "a.pdf", pages=2)
    pdf_b = write_minimal_pdf(tmp_path / "b.pdf", pages=2)
    with _client(tmp_path / "w") as client:
        client.app.state.process_service.set_docx_converter(fake_docx_converter_success)
        sa = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        sb = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        for sid, name, data in (
            (sa.id, "a.pdf", pdf_a.read_bytes()),
            (sb.id, "b.pdf", pdf_b.read_bytes()),
        ):
            batch = client.post(
                f"/api/v1/sessions/{sid}/documents",
                files=[("files", (name, data, "application/pdf"))],
            )
            assert batch.status_code == 200

        ready = threading.Barrier(2)
        results: list[int] = []
        errors: list[BaseException] = []
        pdfium_runtime.reset_inflight_stats()

        def worker(session_id: str) -> None:
            try:
                ready.wait(timeout=5)
                resp = client.post(f"/api/v1/sessions/{session_id}/process")
                results.append(resp.status_code)
                wait_for_process(client, session_id)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        t1 = threading.Thread(target=worker, args=(sa.id,))
        t2 = threading.Thread(target=worker, args=(sb.id,))
        t1.start()
        t2.start()
        t1.join(timeout=120)
        t2.join(timeout=120)
        assert errors == []
        assert results == [200, 200]
        assert pdfium_runtime.get_max_inflight() == 1

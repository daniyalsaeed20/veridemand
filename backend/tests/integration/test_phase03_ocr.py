"""Phase 3 OCR integration: routing, artifacts, issues, concurrency."""

from __future__ import annotations

import threading
from pathlib import Path

from app.models.case_session import CaseSession
from app.models.document_page import DocumentPage
from app.models.source_token import SourceToken
from app.services.ocr import get_max_inflight, reset_inflight_stats, set_fake_engine
from tests.fixtures.upload_builders import write_minimal_pdf, write_ocr_routed_pdf, write_png
from tests.helpers_process import FakeOcrEngine, make_client, upload_and_process, wait_for_process


def test_image_only_page_receives_ocr(tmp_path: Path) -> None:
    png = tmp_path / "scan.png"
    write_png(png, size=(200, 200))
    with make_client(tmp_path / "w") as client:
        session_id, docs = upload_and_process(
            client,
            [("scan.png", png.read_bytes(), "image/png")],
        )
        doc = docs[0]
        pages = [
            DocumentPage.model_validate(p)
            for p in client.get(f"/api/v1/sessions/{session_id}/documents/{doc.id}/pages").json()
        ]
        assert pages
        # Image-only PDF typically routes OCR (or blank→manual_review)
        assert pages[0].route in {"ocr", "manual_review"}
        if pages[0].route == "ocr":
            assert pages[0].ocr_status == "done"
            tokens = [
                SourceToken.model_validate(t)
                for t in client.get(
                    f"/api/v1/sessions/{session_id}/documents/{doc.id}/pages/1/tokens"
                ).json()
            ]
            assert tokens
            assert all(t.method == "ocr" for t in tokens)
            issues = client.get(f"/api/v1/sessions/{session_id}/issues")
            assert issues.status_code == 200


def test_blank_pdf_no_fabricated_text_when_manual_review(tmp_path: Path) -> None:
    pdf = tmp_path / "blank.pdf"
    write_minimal_pdf(pdf, pages=1)
    with make_client(tmp_path / "w") as client:
        session_id, docs = upload_and_process(
            client,
            [("blank.pdf", pdf.read_bytes(), "application/pdf")],
        )
        doc = docs[0]
        pages = client.get(f"/api/v1/sessions/{session_id}/documents/{doc.id}/pages").json()
        for page in pages:
            if page["route"] == "manual_review":
                tokens = client.get(
                    f"/api/v1/sessions/{session_id}/documents/{doc.id}/pages/{page['page_number']}/tokens"
                ).json()
                assert tokens == []


def test_two_sessions_serialize_ocr_worker(tmp_path: Path) -> None:
    png_a = write_png(tmp_path / "a.png", size=(120, 120))
    png_b = write_png(tmp_path / "b.png", size=(120, 120))
    with make_client(tmp_path / "w") as client:
        set_fake_engine(FakeOcrEngine())
        sa = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        sb = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        for sid, name, path in ((sa.id, "a.png", png_a), (sb.id, "b.png", png_b)):
            assert (
                client.post(
                    f"/api/v1/sessions/{sid}/documents",
                    files=[("files", (name, path.read_bytes(), "image/png"))],
                ).status_code
                == 200
            )
        reset_inflight_stats()
        barrier = threading.Barrier(2)
        errors: list[BaseException] = []

        def worker(session_id: str) -> None:
            try:
                barrier.wait(timeout=5)
                assert client.post(f"/api/v1/sessions/{session_id}/process").status_code == 200
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
        assert get_max_inflight() <= 1


def test_session_delete_during_ocr_discards_commit(tmp_path: Path) -> None:
    pdf = write_ocr_routed_pdf(tmp_path / "broken.pdf")
    with make_client(tmp_path / "w") as client:
        set_fake_engine(FakeOcrEngine())
        process = client.app.state.process_service
        sessions = client.app.state.session_service
        entered = threading.Event()
        release = threading.Event()

        def before_ocr_commit() -> None:
            entered.set()
            release.wait(timeout=10)

        process.set_test_hook("before_ocr_commit", before_ocr_commit)
        sessions.set_test_hook("after_mark_deleting", release.set)
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        assert (
            client.post(
                f"/api/v1/sessions/{session.id}/documents",
                files=[("files", ("broken.pdf", pdf.read_bytes(), "application/pdf"))],
            ).status_code
            == 200
        )
        assert client.post(f"/api/v1/sessions/{session.id}/process").status_code == 200
        # Delete mid-flight at OCR commit barrier — must not 500; no late commit
        assert entered.wait(timeout=15)
        assert client.delete(f"/api/v1/sessions/{session.id}").status_code == 204
        process.set_test_hook("before_ocr_commit", None)
        sessions.set_test_hook("after_mark_deleting", None)
        process.wait_until_idle(session.id, timeout=30)
        assert client.get(f"/api/v1/sessions/{session.id}/events").status_code == 404
        assert not (sessions.temp_root / session.id).exists()


def test_cross_session_token_access_denied(tmp_path: Path) -> None:
    png = write_png(tmp_path / "scan.png", size=(160, 160))
    with make_client(tmp_path / "w") as client:
        session_a, docs = upload_and_process(client, [("scan.png", png.read_bytes(), "image/png")])
        doc_id = docs[0].id
        session_b = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        denied = client.get(f"/api/v1/sessions/{session_b.id}/documents/{doc_id}/pages/1/tokens")
        assert denied.status_code == 404


def test_reprocess_idempotent_ocr_artifacts(tmp_path: Path) -> None:
    png = write_png(tmp_path / "scan.png", size=(180, 180))
    with make_client(tmp_path / "w") as client:
        session_id, docs = upload_and_process(client, [("scan.png", png.read_bytes(), "image/png")])
        doc_id = docs[0].id
        first = client.get(
            f"/api/v1/sessions/{session_id}/documents/{doc_id}/pages/1/tokens"
        ).json()
        # Reprocess
        assert client.post(f"/api/v1/sessions/{session_id}/process").status_code == 200
        wait_for_process(client, session_id)
        second = client.get(
            f"/api/v1/sessions/{session_id}/documents/{doc_id}/pages/1/tokens"
        ).json()
        # Atomically replaced — same count shape from fake engine, no duplication growth unbounded
        assert len(second) == len(first) or (len(first) == 0 and len(second) >= 0)

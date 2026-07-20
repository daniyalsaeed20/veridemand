"""B-02 DELETE-during-process race and stress tests (barrier-based)."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

from app.models.case_session import CaseSession
from app.services.ocr import set_fake_engine
from tests.fixtures.upload_builders import write_ocr_routed_pdf, write_png
from tests.helpers_process import FakeOcrEngine, make_client


def test_delete_during_normalize_never_500(tmp_path: Path) -> None:
    png = write_png(tmp_path / "scan.png", size=(160, 160))
    with make_client(tmp_path / "w") as client:
        set_fake_engine(FakeOcrEngine())
        process = client.app.state.process_service
        sessions = client.app.state.session_service
        entered = threading.Event()
        release = threading.Event()

        def before_write() -> None:
            entered.set()
            release.wait(timeout=10)

        process.set_test_hook("before_workspace_write", before_write)
        # Avoid deadlock: DELETE drain joins process; release when tombstone is set.
        sessions.set_test_hook("after_mark_deleting", release.set)

        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        assert (
            client.post(
                f"/api/v1/sessions/{session.id}/documents",
                files=[("files", ("scan.png", png.read_bytes(), "image/png"))],
            ).status_code
            == 200
        )
        assert client.post(f"/api/v1/sessions/{session.id}/process").status_code == 200
        assert entered.wait(timeout=10)
        resp = client.delete(f"/api/v1/sessions/{session.id}")
        assert resp.status_code == 204
        assert client.get(f"/api/v1/sessions/{session.id}/events").status_code == 404
        process.wait_until_idle(session.id, timeout=30)
        process.set_test_hook("before_workspace_write", None)
        sessions.set_test_hook("after_mark_deleting", None)
        assert not (sessions.temp_root / session.id).exists()


def test_delete_before_ocr_commit_discards(tmp_path: Path) -> None:
    pdf = write_ocr_routed_pdf(tmp_path / "broken.pdf")
    with make_client(tmp_path / "w") as client:
        set_fake_engine(FakeOcrEngine())
        process = client.app.state.process_service
        sessions = client.app.state.session_service
        entered = threading.Event()
        release = threading.Event()

        def before_commit() -> None:
            entered.set()
            release.wait(timeout=10)

        process.set_test_hook("before_ocr_commit", before_commit)
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
        assert entered.wait(timeout=15)
        resp = client.delete(f"/api/v1/sessions/{session.id}")
        assert resp.status_code == 204
        process.set_test_hook("before_ocr_commit", None)
        sessions.set_test_hook("after_mark_deleting", None)
        process.wait_until_idle(session.id, timeout=30)
        assert client.get(f"/api/v1/sessions/{session.id}/events").status_code == 404
        assert not (sessions.temp_root / session.id).exists()


def test_delete_idempotent_double(tmp_path: Path) -> None:
    png = write_png(tmp_path / "scan.png", size=(120, 120))
    with make_client(tmp_path / "w") as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        assert (
            client.post(
                f"/api/v1/sessions/{session.id}/documents",
                files=[("files", ("scan.png", png.read_bytes(), "image/png"))],
            ).status_code
            == 200
        )
        assert client.delete(f"/api/v1/sessions/{session.id}").status_code == 204
        assert client.delete(f"/api/v1/sessions/{session.id}").status_code == 204


def test_delete_during_process_stress_100(tmp_path: Path) -> None:
    """Previously failing race: zero HTTP 500 across 100 controlled iterations."""
    png = write_png(tmp_path / "scan.png", size=(140, 140))
    status_counts: dict[int, int] = {}
    for i in range(100):
        run = tmp_path / f"run_{i}"
        if run.exists():
            shutil.rmtree(run, ignore_errors=True)
        run.mkdir(parents=True)
        with make_client(run) as client:
            set_fake_engine(FakeOcrEngine())
            process = client.app.state.process_service
            sessions = client.app.state.session_service
            session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
            assert (
                client.post(
                    f"/api/v1/sessions/{session.id}/documents",
                    files=[("files", ("scan.png", png.read_bytes(), "image/png"))],
                ).status_code
                == 200
            )
            hold: threading.Event | None = None
            if i % 3 == 0:
                hold = threading.Event()
                entered = threading.Event()

                def before(
                    entered_ev: threading.Event = entered,
                    hold_ev: threading.Event = hold,
                ) -> None:
                    entered_ev.set()
                    hold_ev.wait(timeout=5)

                process.set_test_hook("before_workspace_write", before)
                sessions.set_test_hook("after_mark_deleting", hold.set)
                assert client.post(f"/api/v1/sessions/{session.id}/process").status_code == 200
                assert entered.wait(timeout=10)
                resp = client.delete(f"/api/v1/sessions/{session.id}")
                process.set_test_hook("before_workspace_write", None)
                sessions.set_test_hook("after_mark_deleting", None)
            else:
                assert client.post(f"/api/v1/sessions/{session.id}/process").status_code == 200
                resp = client.delete(f"/api/v1/sessions/{session.id}")
            status_counts[resp.status_code] = status_counts.get(resp.status_code, 0) + 1
            assert resp.status_code == 204, f"iter {i} got {resp.status_code}"
            assert client.get(f"/api/v1/sessions/{session.id}/events").status_code == 404
            process.wait_until_idle(session.id, timeout=30)
            ws = sessions.temp_root / session.id
            assert not ws.exists(), f"orphan workspace at iter {i}"
    assert status_counts.get(500, 0) == 0
    assert status_counts.get(204, 0) == 100

"""Classification lifecycle race tests (DELETE/expiry during classify commit)."""

from __future__ import annotations

import threading
from pathlib import Path

from tests.fixtures.upload_builders import write_police_report_pdf
from tests.helpers_process import make_client


def test_delete_during_classification_discards_late_commit(tmp_path: Path) -> None:
    police = tmp_path / "police.pdf"
    write_police_report_pdf(police)
    with make_client(tmp_path) as client:
        session = client.post("/api/v1/sessions").json()
        session_id = session["id"]
        client.post(
            f"/api/v1/sessions/{session_id}/documents",
            files=[("files", ("police.pdf", police.read_bytes(), "application/pdf"))],
        )

        classification = client.app.state.classification_service
        barrier = threading.Barrier(2)

        def before_classification_commit() -> None:
            barrier.wait(timeout=5)

        classification.set_test_hook("before_classification_commit", before_classification_commit)

        def run_process() -> None:
            client.post(f"/api/v1/sessions/{session_id}/process")

        worker = threading.Thread(target=run_process)
        worker.start()
        barrier.wait(timeout=5)

        delete_resp = client.delete(f"/api/v1/sessions/{session_id}")
        assert delete_resp.status_code == 204

        worker.join(timeout=30)
        client.app.state.process_service.wait_until_idle(session_id, timeout=30)

        get_resp = client.get(f"/api/v1/sessions/{session_id}")
        assert get_resp.status_code in {404, 410}

        classification.set_test_hook("before_classification_commit", None)


def test_delete_during_classification_no_500(tmp_path: Path) -> None:
    """Stress: DELETE during classification must not return HTTP 500."""
    for _ in range(10):
        test_delete_during_classification_discards_late_commit(tmp_path)

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.app.contracts.identifiers import new_session_id
from backend.app.main import create_app
from backend.app.settings.config import Settings
from backend.app.storage import paths

_API = "/api/v1"


def _create_session(client: TestClient) -> str:
    response = client.post(f"{_API}/sessions")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["session_id"].startswith("ses_")
    assert body["runtime_warning"]
    return str(body["session_id"])


def _upload(
    client: TestClient, session_id: str, uploads_dir: Path, names: list[str]
) -> dict[str, Any]:
    files = [
        ("files", (name, (uploads_dir / name).read_bytes(), "application/octet-stream"))
        for name in names
    ]
    response = client.post(f"{_API}/sessions/{session_id}/documents", files=files)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _poll_snapshot(
    client: TestClient,
    session_id: str,
    predicate: Callable[[dict[str, Any]], bool],
    timeout: float = 5.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    body: dict[str, Any] = {}
    while time.monotonic() < deadline:
        body = client.get(f"{_API}/sessions/{session_id}").json()
        if predicate(body):
            return body
        time.sleep(0.05)
    return body


def test_create_and_get_session(client: TestClient) -> None:
    session_id = _create_session(client)
    response = client.get(f"{_API}/sessions/{session_id}")
    assert response.status_code == 200
    assert response.json()["session_id"] == session_id


def test_get_unknown_session_returns_404(client: TestClient) -> None:
    response = client.get(f"{_API}/sessions/{new_session_id()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "session_not_found"


def test_upload_partial_acceptance(client: TestClient, uploads_dir: Path) -> None:
    session_id = _create_session(client)
    body = _upload(client, session_id, uploads_dir, ["valid.png", "corrupt.pdf"])
    assert len(body["accepted"]) == 1
    assert len(body["rejected"]) == 1
    assert body["rejected"][0]["error_code"] == "upload_corrupt_file"
    assert body["session"]["counts"]["uploaded"] == 1


def test_upload_with_no_files_is_rejected(client: TestClient) -> None:
    session_id = _create_session(client)
    response = client.post(f"{_API}/sessions/{session_id}/documents", files=[])
    # FastAPI validates the required multipart field before our handler.
    assert response.status_code in (400, 422)


def test_process_and_reach_ready(client: TestClient, uploads_dir: Path) -> None:
    session_id = _create_session(client)
    _upload(client, session_id, uploads_dir, ["valid_utf8.txt", "valid_utf8.txt"])

    response = client.post(f"{_API}/sessions/{session_id}/process", json={"document_ids": None})
    assert response.status_code == 202
    assert len(response.json()["queued"]) == 2

    terminal = {
        "visual_processing_complete",
        "visual_processing_partial",
        "visual_processing_failed",
    }

    def _done(snapshot: dict[str, object]) -> bool:
        counts = snapshot.get("counts")
        if not isinstance(counts, dict):
            return False
        total = sum(int(counts.get(key, 0) or 0) for key in terminal)
        return total == 2

    body = _poll_snapshot(client, session_id, _done)
    for document in body["documents"]:
        assert document["progress_percent"] <= 65
        assert document["result_available"] is False
        assert document["extraction_performed"] is False
        assert document["canonical_view_available"] is True
        assert document["status"] in terminal
        assert document["progress_percent"] == 65


def test_jobs_listed_after_process(client: TestClient, uploads_dir: Path) -> None:
    session_id = _create_session(client)
    _upload(client, session_id, uploads_dir, ["valid_utf8.txt"])
    client.post(f"{_API}/sessions/{session_id}/process", json={"document_ids": None})

    _poll_snapshot(
        client,
        session_id,
        lambda s: (
            (
                int(s["counts"].get("visual_processing_complete", 0) or 0)
                + int(s["counts"].get("visual_processing_partial", 0) or 0)
                + int(s["counts"].get("visual_processing_failed", 0) or 0)
            )
            == 1
        ),
    )
    jobs = client.get(f"{_API}/sessions/{session_id}/jobs").json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["status"] == "completed"


def test_remove_document(client: TestClient, uploads_dir: Path) -> None:
    session_id = _create_session(client)
    body = _upload(client, session_id, uploads_dir, ["valid.png"])
    document_id = body["accepted"][0]["document_id"]

    response = client.delete(f"{_API}/sessions/{session_id}/documents/{document_id}")
    assert response.status_code == 204

    snapshot = client.get(f"{_API}/sessions/{session_id}").json()
    assert snapshot["documents"] == []


def test_delete_session_removes_storage(settings: Settings, uploads_dir: Path) -> None:
    with TestClient(create_app(settings)) as client:
        session_id = _create_session(client)
        _upload(client, session_id, uploads_dir, ["valid.png"])
        session_root = paths.session_dir(settings.temp_root, session_id)
        assert session_root.exists()

        response = client.delete(f"{_API}/sessions/{session_id}")
        assert response.status_code == 204
        assert not session_root.exists()

        assert client.get(f"{_API}/sessions/{session_id}").status_code == 404


def test_file_count_limit_via_api(tmp_path: Path, uploads_dir: Path) -> None:
    limited = Settings(temp_root=tmp_path / "temp", max_files_per_session=1)
    with TestClient(create_app(limited)) as client:
        session_id = _create_session(client)
        body = _upload(client, session_id, uploads_dir, ["valid.png", "valid.jpeg"])
        assert len(body["accepted"]) == 1
        assert len(body["rejected"]) == 1
        assert body["rejected"][0]["error_code"] == "session_limit_exceeded"


def test_session_expires_after_ttl(tmp_path: Path) -> None:
    short = Settings(
        temp_root=tmp_path / "temp",
        session_ttl_seconds=2,
        session_cleanup_interval_seconds=1,
        session_expiring_warning_seconds=1,
    )
    with TestClient(create_app(short)) as client:
        response = client.post(f"{_API}/sessions")
        session_id = response.json()["session_id"]
        session_root = paths.session_dir(short.temp_root, session_id)
        assert session_root.exists()

        # Do not touch the session; wait past its TTL.
        time.sleep(3.5)

        expired = client.get(f"{_API}/sessions/{session_id}")
        assert expired.status_code == 404
        assert expired.json()["error"]["code"] in ("session_expired", "session_not_found")
        assert not session_root.exists()


def test_startup_sweep_removes_abandoned_dirs(tmp_path: Path) -> None:
    settings = Settings(temp_root=tmp_path / "temp")
    stray_id = new_session_id()
    stray_dir = paths.session_dir(settings.temp_root, stray_id)
    (stray_dir / "originals").mkdir(parents=True)

    with TestClient(create_app(settings)):
        # Lifespan startup sweep runs on enter.
        assert not stray_dir.exists()


def test_sse_connection_limit(tmp_path: Path) -> None:
    # Streaming SSE responses cannot be held open cleanly under TestClient, so we
    # occupy the connection budget by registering a subscriber directly on the
    # broker (via the app's event loop) and then assert the endpoint rejects the
    # next HTTP subscriber with a 429.
    settings = Settings(temp_root=tmp_path / "temp", max_sse_connections_per_session=1)
    app = create_app(settings)
    with TestClient(app) as client:
        session_id = _create_session(client)
        registry = app.state.session_registry
        broker = registry.peek(session_id).broker
        assert client.portal is not None
        client.portal.call(broker.connect, None)  # fills the single connection slot

        response = client.get(f"{_API}/sessions/{session_id}/events")
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "sse_connection_limit"


def test_sse_headers_and_media_type() -> None:
    # Validate the SSE content type and no-store headers without opening a live
    # stream (EventSourceResponse guarantees the media type; the endpoint sets the
    # cache/buffering headers).
    from sse_starlette.sse import EventSourceResponse

    from backend.app.api.v1.endpoints.sessions import _SSE_HEADERS

    async def _gen() -> AsyncIterator[dict[str, str]]:
        yield {"data": "x"}

    response = EventSourceResponse(_gen(), headers=_SSE_HEADERS)
    assert response.media_type == "text/event-stream"
    assert _SSE_HEADERS["Cache-Control"] == "no-store"
    assert _SSE_HEADERS["X-Accel-Buffering"] == "no"

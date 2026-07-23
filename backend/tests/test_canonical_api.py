from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.settings.config import Settings

_API = "/api/v1"
_LO_PATH = Path(r"D:\programming\tools\libreoffice\program\soffice.com")


def _create_session(client: TestClient) -> str:
    response = client.post(f"{_API}/sessions")
    assert response.status_code == 201, response.text
    return str(response.json()["session_id"])


def _upload(
    client: TestClient, session_id: str, uploads_dir: Path, names: list[str]
) -> dict[str, Any]:
    files = [
        ("files", (name, (uploads_dir / name).read_bytes(), "application/octet-stream"))
        for name in names
    ]
    response = client.post(f"{_API}/sessions/{session_id}/documents", files=files)
    assert response.status_code == 201, response.text
    payload: dict[str, Any] = response.json()
    return payload


def _poll_snapshot(
    client: TestClient,
    session_id: str,
    predicate: Callable[[dict[str, Any]], bool],
    timeout: float = 10.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    body: dict[str, Any] = {}
    while time.monotonic() < deadline:
        body = client.get(f"{_API}/sessions/{session_id}").json()
        if predicate(body):
            return body
        time.sleep(0.05)
    return body


def _process_pdf_to_ready(
    client: TestClient, uploads_dir: Path, filename: str = "valid_single_page.pdf"
) -> tuple[str, str]:
    session_id = _create_session(client)
    body = _upload(client, session_id, uploads_dir, [filename])
    document_id = str(body["accepted"][0]["document_id"])
    response = client.post(f"{_API}/sessions/{session_id}/process", json={"document_ids": None})
    assert response.status_code == 202
    _poll_snapshot(
        client,
        session_id,
        lambda snapshot: snapshot["counts"].get("ready_for_extraction", 0) >= 1,
    )
    return session_id, document_id


def test_get_canonical_pdf_returns_200(client: TestClient, uploads_dir: Path) -> None:
    session_id, document_id = _process_pdf_to_ready(client, uploads_dir)
    response = client.get(f"{_API}/sessions/{session_id}/documents/{document_id}/canonical")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers.get("accept-ranges") == "bytes"
    assert response.content.startswith(b"%PDF")


def test_get_canonical_pdf_range_returns_206(client: TestClient, uploads_dir: Path) -> None:
    session_id, document_id = _process_pdf_to_ready(client, uploads_dir)
    full = client.get(f"{_API}/sessions/{session_id}/documents/{document_id}/canonical").content
    response = client.get(
        f"{_API}/sessions/{session_id}/documents/{document_id}/canonical",
        headers={"Range": "bytes=0-15"},
    )
    assert response.status_code == 206
    assert response.content == full[:16]
    assert response.headers["content-range"] == f"bytes 0-15/{len(full)}"
    assert response.headers["content-length"] == "16"
    assert response.headers.get("accept-ranges") == "bytes"


def test_get_canonical_pdf_open_ended_range(client: TestClient, uploads_dir: Path) -> None:
    session_id, document_id = _process_pdf_to_ready(client, uploads_dir)
    full = client.get(f"{_API}/sessions/{session_id}/documents/{document_id}/canonical").content
    start = max(0, len(full) - 32)
    response = client.get(
        f"{_API}/sessions/{session_id}/documents/{document_id}/canonical",
        headers={"Range": f"bytes={start}-"},
    )
    assert response.status_code == 206
    expected = full[start:]
    assert response.content == expected
    assert len(response.content) == len(expected)
    assert response.headers["content-length"] == str(len(expected))
    assert response.headers["content-range"] == f"bytes {start}-{len(full) - 1}/{len(full)}"


def test_get_canonical_pdf_range_bytes_must_match_slice(
    client: TestClient, uploads_dir: Path
) -> None:
    """Regression: a 206 with wrong payload length or wrong slice must fail."""

    session_id, document_id = _process_pdf_to_ready(client, uploads_dir)
    full = client.get(f"{_API}/sessions/{session_id}/documents/{document_id}/canonical").content
    assert len(full) > 64
    response = client.get(
        f"{_API}/sessions/{session_id}/documents/{document_id}/canonical",
        headers={"Range": "bytes=10-41"},
    )
    assert response.status_code == 206
    assert response.content == full[10:42]
    assert int(response.headers["content-length"]) == len(response.content)
    # Deliberately assert inequality against a wrong slice so the test fails
    # if the server ever returns the wrong window.
    assert response.content != full[0:32]
    assert response.content != full[11:43]


def test_get_canonical_pdf_bad_range_returns_416(client: TestClient, uploads_dir: Path) -> None:
    session_id, document_id = _process_pdf_to_ready(client, uploads_dir)
    response = client.get(
        f"{_API}/sessions/{session_id}/documents/{document_id}/canonical",
        headers={"Range": "bytes=999999999-"},
    )
    assert response.status_code == 416


def test_get_canonical_metadata_returns_200(client: TestClient, uploads_dir: Path) -> None:
    session_id, document_id = _process_pdf_to_ready(client, uploads_dir)
    response = client.get(
        f"{_API}/sessions/{session_id}/documents/{document_id}/canonical/metadata"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == document_id
    assert body["canonical_status"] == "ready"
    assert body["page_count"] >= 1
    assert len(body["pages"]) == body["page_count"]
    assert body["sha256"]


def test_get_overlay_proof_is_synthetic(client: TestClient, uploads_dir: Path) -> None:
    session_id, document_id = _process_pdf_to_ready(
        client, uploads_dir, filename="valid_multi_page.pdf"
    )
    response = client.get(
        f"{_API}/sessions/{session_id}/documents/{document_id}/canonical/overlay-proof"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["synthetic"] is True
    assert len(body["overlays"]) == 3
    assert all(item["synthetic"] for item in body["overlays"])
    assert body["overlays"][0]["geometry"]["bbox"]["width"] == 0.25


def test_get_canonical_not_ready_returns_409(client: TestClient, uploads_dir: Path) -> None:
    session_id = _create_session(client)
    body = _upload(client, session_id, uploads_dir, ["valid_single_page.pdf"])
    document_id = str(body["accepted"][0]["document_id"])
    for path_suffix in ("canonical", "canonical/metadata", "canonical/overlay-proof"):
        response = client.get(f"{_API}/sessions/{session_id}/documents/{document_id}/{path_suffix}")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "canonical_document_not_ready"


def test_readiness_includes_libreoffice_when_configured(tmp_path: Path) -> None:
    if _LO_PATH.is_file():
        settings = Settings(
            temp_root=tmp_path / "temp",
            libreoffice_executable=str(_LO_PATH),
            ocr_enabled=False,
        )
    else:
        settings = Settings(temp_root=tmp_path / "temp", ocr_enabled=False)
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    checks = {item["name"]: item for item in response.json()["checks"]}
    assert checks["libreoffice"]["status"] == "pass"
    assert checks["reportlab"]["status"] == "pass"

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


def test_get_canonical_pdf_range_1024_and_sha256_stable(
    client: TestClient, uploads_dir: Path, tmp_path: Path
) -> None:
    """Phase 4.4: exact 0-1023 range + PDF integrity markers."""

    from pypdf import PdfWriter

    # Synthetic uploads are tiny; build a >1KiB PDF so Range 0-1023 is valid.
    large_pdf = tmp_path / "large_range.pdf"
    writer = PdfWriter()
    for _ in range(8):
        writer.add_blank_page(width=612, height=792)
    # Pad with an embedded stream so the file exceeds 1024 bytes.
    with large_pdf.open("wb") as handle:
        writer.write(handle)
    if large_pdf.stat().st_size <= 1024:
        # Extremely defensive: append comment padding if blank pages stay tiny.
        padded = large_pdf.read_bytes() + (b"\n% " + (b"x" * 1200) + b"\n")
        large_pdf.write_bytes(padded)

    session_id = _create_session(client)
    files = [("files", ("large_range.pdf", large_pdf.read_bytes(), "application/pdf"))]
    upload = client.post(f"{_API}/sessions/{session_id}/documents", files=files)
    assert upload.status_code == 201, upload.text
    document_id = str(upload.json()["accepted"][0]["document_id"])
    response = client.post(f"{_API}/sessions/{session_id}/process", json={"document_ids": None})
    assert response.status_code == 202
    _poll_snapshot(
        client,
        session_id,
        lambda snapshot: snapshot["counts"].get("ready_for_extraction", 0) >= 1,
    )

    meta = client.get(f"{_API}/sessions/{session_id}/documents/{document_id}/canonical/metadata")
    assert meta.status_code == 200
    sha_before = meta.json()["sha256"]
    full = client.get(f"{_API}/sessions/{session_id}/documents/{document_id}/canonical")
    assert full.status_code == 200
    assert full.headers["content-type"].startswith("application/pdf")
    assert full.headers.get("accept-ranges") == "bytes"
    assert full.content.startswith(b"%PDF")
    assert int(full.headers["content-length"]) == len(full.content)
    assert len(full.content) > 1024

    ranged = client.get(
        f"{_API}/sessions/{session_id}/documents/{document_id}/canonical",
        headers={"Range": "bytes=0-1023"},
    )
    assert ranged.status_code == 206
    assert ranged.headers["content-type"].startswith("application/pdf")
    assert ranged.headers.get("accept-ranges") == "bytes"
    assert ranged.headers["content-length"] == "1024"
    assert ranged.headers["content-range"] == f"bytes 0-1023/{len(full.content)}"
    assert ranged.content == full.content[:1024]

    meta_after = client.get(
        f"{_API}/sessions/{session_id}/documents/{document_id}/canonical/metadata"
    )
    assert meta_after.json()["sha256"] == sha_before


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

"""Process endpoint rejects when OCR is enabled but the worker is not ready."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.settings.config import Settings

_API = "/api/v1"


@pytest.fixture
def ocr_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("VERIDEMAND_SKIP_OCR_WORKER", "1")
    settings = Settings(
        temp_root=tmp_path / "temp",
        ocr_enabled=True,
        render_concurrency=1,
        ocr_concurrency=1,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def test_process_rejects_when_ocr_worker_not_ready(
    ocr_client: TestClient, uploads_dir: Path
) -> None:
    created = ocr_client.post(f"{_API}/sessions")
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    files = [
        (
            "files",
            (
                "valid_single_page.pdf",
                (uploads_dir / "valid_single_page.pdf").read_bytes(),
                "application/pdf",
            ),
        )
    ]
    upload = ocr_client.post(f"{_API}/sessions/{session_id}/documents", files=files)
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["accepted"][0]["document_id"]

    response = ocr_client.post(
        f"{_API}/sessions/{session_id}/process",
        json={"document_ids": [document_id]},
    )
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "ocr_worker_not_ready"
    assert "Printed OCR is still starting or unavailable" in body["error"]["message"]

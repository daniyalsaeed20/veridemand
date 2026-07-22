"""Integration tests for native extraction API flows."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import create_app
from backend.app.settings.config import Settings

GOOD_BYTES = Path("fixtures/synthetic/native/good-native-single-page.pdf").read_bytes()
BAD_BYTES = Path("fixtures/synthetic/native/replacement-character-layer.pdf").read_bytes()
IMAGE_BYTES = Path("fixtures/synthetic/native/image-only.pdf").read_bytes()


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    settings = Settings(temp_root=tmp_path / "temp")
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://test") as ac,
    ):
        yield ac


async def _wait_native(
    client: AsyncClient, session_id: str, document_id: str
) -> dict[str, object]:
    import asyncio

    for _ in range(400):
        response = await client.get(f"/api/v1/sessions/{session_id}/documents/{document_id}")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, dict)
        if body["status"] in {"native_trust_complete", "failed", "cancelled"}:
            return body
        await asyncio.sleep(0.05)
    raise AssertionError("timed out waiting for native trust")


async def test_good_native_api_flow(client: AsyncClient) -> None:
    session = (await client.post("/api/v1/sessions")).json()
    session_id = session["session_id"]
    files = {"files": ("good.pdf", GOOD_BYTES, "application/pdf")}
    upload = await client.post(f"/api/v1/sessions/{session_id}/documents", files=files)
    assert upload.status_code == 201
    document_id = upload.json()["accepted"][0]["document_id"]
    process = await client.post(
        f"/api/v1/sessions/{session_id}/process", json={"document_ids": None}
    )
    assert process.status_code == 202
    doc = await _wait_native(client, session_id, document_id)
    assert doc["status"] == "native_trust_complete", doc
    assert doc["progress_percent"] == 35
    assert doc["native_result_available"] is True
    assert doc["document_source_policy"] == "native_authority"

    summary = await client.get(
        f"/api/v1/sessions/{session_id}/documents/{document_id}/native/summary"
    )
    assert summary.status_code == 200
    assert summary.json()["pages_accepted"] >= 1
    assert summary.json()["final_result_available"] is False

    page = await client.get(f"/api/v1/sessions/{session_id}/documents/{document_id}/native/pages/1")
    assert page.status_code == 200
    body = page.json()
    assert body["decision"] == "accepted"
    assert body["words"]
    assert body["characters"] == []

    page_chars = await client.get(
        f"/api/v1/sessions/{session_id}/documents/{document_id}/native/pages/1",
        params={"include_characters": "true"},
    )
    assert page_chars.json()["characters"]


async def test_bad_native_api_flow(client: AsyncClient) -> None:
    session = (await client.post("/api/v1/sessions")).json()
    session_id = session["session_id"]
    files = {"files": ("bad.pdf", BAD_BYTES, "application/pdf")}
    upload = await client.post(f"/api/v1/sessions/{session_id}/documents", files=files)
    assert upload.status_code == 201
    document_id = upload.json()["accepted"][0]["document_id"]
    await client.post(f"/api/v1/sessions/{session_id}/process", json={"document_ids": None})
    doc = await _wait_native(client, session_id, document_id)
    assert doc["status"] == "native_trust_complete", doc
    assert doc["native_result_available"] is False
    assert doc["visual_processing_required"] is True

    page = await client.get(f"/api/v1/sessions/{session_id}/documents/{document_id}/native/pages/1")
    body = page.json()
    assert body["decision"] in {"rejected", "absent", "error"}
    assert body["words"] == []
    assert body["characters"] == []
    assert body.get("provisional_native_text") in (None, "")


async def test_image_only_api_flow(client: AsyncClient) -> None:
    session = (await client.post("/api/v1/sessions")).json()
    session_id = session["session_id"]
    files = {"files": ("image.pdf", IMAGE_BYTES, "application/pdf")}
    upload = await client.post(f"/api/v1/sessions/{session_id}/documents", files=files)
    assert upload.status_code == 201
    document_id = upload.json()["accepted"][0]["document_id"]
    await client.post(f"/api/v1/sessions/{session_id}/process", json={"document_ids": None})
    doc = await _wait_native(client, session_id, document_id)
    assert doc["status"] == "native_trust_complete", doc
    assert doc["visual_processing_required"] is True
    page = await client.get(f"/api/v1/sessions/{session_id}/documents/{document_id}/native/pages/1")
    assert page.json()["words"] == []

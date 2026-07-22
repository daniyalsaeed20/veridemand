"""Phase 3.2 containment: page-level parser errors must not fail the job."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.app.contracts.errors import ErrorCode
from backend.app.extraction.native.errors import NativeExtractionError
from backend.app.extraction.native.models import (
    CanonicalPageRef,
    NativeTrustPolicyConfig,
    NativeWorkerRequest,
)
from backend.app.extraction.native.runner import NativeExtractionRunner
from backend.app.main import create_app
from backend.app.settings.config import Settings

PARSER_PAGE = Path("fixtures/synthetic/native/parser-error-page.pdf")
GOOD_WITH_BAD = Path("fixtures/synthetic/native/good-with-one-parser-error.pdf")
CORRUPT = Path("fixtures/synthetic/native/replacement-character-layer.pdf")
MIXED = Path("fixtures/synthetic/native/mixed-native-image.pdf")
GOOD = Path("fixtures/synthetic/native/good-native-single-page.pdf")
CORRUPT_BYTES = CORRUPT.read_bytes()
MIXED_BYTES = MIXED.read_bytes()
GOOD_BYTES = GOOD.read_bytes()


@pytest.fixture
async def app_client(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, AsyncClient]]:
    settings = Settings(temp_root=tmp_path / "temp")
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://test") as ac,
    ):
        yield app, ac


async def _wait(client: AsyncClient, session_id: str, document_id: str) -> dict[str, object]:
    import asyncio

    for _ in range(600):
        body = (await client.get(f"/api/v1/sessions/{session_id}/documents/{document_id}")).json()
        assert isinstance(body, dict)
        if body["status"] in {"native_trust_complete", "failed", "cancelled"}:
            return body
        await asyncio.sleep(0.05)
    raise AssertionError("timed out")


def _pages_for(pdf: Path) -> list[CanonicalPageRef]:
    import pdfplumber

    pages: list[CanonicalPageRef] = []
    with pdfplumber.open(pdf) as doc:
        for i, page in enumerate(doc.pages):
            pages.append(CanonicalPageRef(i + 1, float(page.width), float(page.height), 0, "pdf"))
    return pages


def test_page_level_parser_error_worker_exits_zero(tmp_path: Path) -> None:
    import asyncio

    pdf = GOOD_WITH_BAD if GOOD_WITH_BAD.is_file() else PARSER_PAGE

    async def _run() -> None:
        request = NativeWorkerRequest(
            session_id="ses_" + ("a" * 32),
            document_id="doc_" + ("b" * 32),
            job_id="job_" + ("c" * 32),
            canonical_pdf_path=str(pdf.resolve()),
            canonicalisation_method="original_pdf",
            pages=_pages_for(pdf),
            policy=NativeTrustPolicyConfig(),
        )
        outcome = await NativeExtractionRunner(timeout_seconds=120, grace_seconds=2).run(
            request, staging_dir=tmp_path / "staging"
        )
        assert outcome.exit_code == 0
        assert outcome.summary.native_processing_status.value == "complete"
        if pdf == GOOD_WITH_BAD:
            assert outcome.summary.pages_accepted >= 1
            assert (
                outcome.summary.pages_errored
                + outcome.summary.pages_rejected
                + outcome.summary.pages_absent
            ) >= 1
            for page in outcome.pages:
                if page.decision.value != "accepted":
                    assert page.words == []
                    assert page.characters == []
                    assert not page.provisional_native_text

    asyncio.run(_run())


async def test_corrupt_single_page_api_visual_authority(
    app_client: tuple[FastAPI, AsyncClient],
) -> None:
    _app, client = app_client
    session = (await client.post("/api/v1/sessions")).json()
    session_id = session["session_id"]
    upload = await client.post(
        f"/api/v1/sessions/{session_id}/documents",
        files={"files": ("corrupt.pdf", CORRUPT_BYTES, "application/pdf")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["accepted"][0]["document_id"]
    await client.post(f"/api/v1/sessions/{session_id}/process", json={"document_ids": None})
    doc = await _wait(client, session_id, document_id)
    assert doc["status"] == "native_trust_complete", doc
    assert doc["document_source_policy"] == "visual_authority"
    page = await client.get(f"/api/v1/sessions/{session_id}/documents/{document_id}/native/pages/1")
    assert page.json()["words"] == []
    assert page.json().get("provisional_native_text") in (None, "")


async def test_mixed_document_reaches_native_trust_complete(
    app_client: tuple[FastAPI, AsyncClient],
) -> None:
    _app, client = app_client
    session = (await client.post("/api/v1/sessions")).json()
    session_id = session["session_id"]
    upload = await client.post(
        f"/api/v1/sessions/{session_id}/documents",
        files={"files": ("mixed.pdf", MIXED_BYTES, "application/pdf")},
    )
    document_id = upload.json()["accepted"][0]["document_id"]
    await client.post(f"/api/v1/sessions/{session_id}/process", json={"document_ids": None})
    doc = await _wait(client, session_id, document_id)
    assert doc["status"] == "native_trust_complete", doc
    assert doc["document_source_policy"] in {
        "mixed_authority",
        "visual_authority",
        "native_authority",
    }


async def test_infrastructure_failure_surfaces_safe_code(
    app_client: tuple[FastAPI, AsyncClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.app.extraction.native import service as native_service_mod

    async def _boom(**_kwargs: object) -> object:
        raise NativeExtractionError(
            ErrorCode.NATIVE_WORKER_START_FAILED,
            "Native extraction worker failed to start.",
            operation="spawn_worker",
            failing_component="NativeExtractionRunner",
        )

    monkeypatch.setattr(
        native_service_mod.NativeExtractionService,
        "extract_document",
        _boom,
        raising=True,
    )
    # Rebuild app so coordinator uses patched class methods... patch instance method instead.
    _app, client = app_client
    monkeypatch.setattr(_app.state.native_service, "extract_document", _boom, raising=True)

    session = (await client.post("/api/v1/sessions")).json()
    session_id = session["session_id"]
    upload = await client.post(
        f"/api/v1/sessions/{session_id}/documents",
        files={"files": ("good.pdf", GOOD_BYTES, "application/pdf")},
    )
    document_id = upload.json()["accepted"][0]["document_id"]
    await client.post(f"/api/v1/sessions/{session_id}/process", json={"document_ids": None})
    doc = await _wait(client, session_id, document_id)
    assert doc["status"] == "failed", doc
    assert doc["failure_code"] == ErrorCode.NATIVE_WORKER_START_FAILED.value
    assert doc["failure_stage"] == "extracting_native"
    assert "could not start or publish" in str(doc["failure_message"]).lower()
    assert doc["canonical_view_available"] is True

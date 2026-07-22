"""HTTP client helpers for the smoke corpus runner."""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx


@dataclass
class ProcessedDocument:
    session_id: str
    document_id: str
    document: dict[str, Any]
    summary: dict[str, Any] | None
    page_results: dict[int, dict[str, Any]] = field(default_factory=dict)
    canonical_ok: bool = False
    canonical_metadata: dict[str, Any] | None = None
    sse_blobs: list[str] = field(default_factory=list)
    public_result_blobs: list[str] = field(default_factory=list)


async def wait_for_document(
    client: httpx.AsyncClient,
    session_id: str,
    document_id: str,
    *,
    timeout_s: float = 60.0,
    poll_s: float = 0.1,
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    consecutive_404 = 0
    while loop.time() < deadline:
        response = await client.get(f"/api/v1/sessions/{session_id}/documents/{document_id}")
        if response.status_code == 404:
            consecutive_404 += 1
            if consecutive_404 >= 30:
                response.raise_for_status()
            await asyncio.sleep(poll_s)
            continue
        consecutive_404 = 0
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise TypeError("document poll response must be an object")
        if body.get("status") in {"native_trust_complete", "failed", "cancelled"}:
            return body
        await asyncio.sleep(poll_s)
    raise TimeoutError(f"timed out waiting for document {document_id}")


async def process_pdf(
    client: httpx.AsyncClient,
    pdf_path: Path,
    *,
    filename: str | None = None,
    fetch_pages: list[int] | None = None,
    include_characters: bool = False,
    collect_sse: bool = False,
) -> ProcessedDocument:
    # Warm the connection — first request against a freshly-started or
    # reload-cycling uvicorn can occasionally 404 before routes are ready.
    for _ in range(20):
        live = await client.get("/health/live")
        if live.status_code == 200:
            break
        await asyncio.sleep(0.1)
    else:
        raise RuntimeError("API /health/live not ready")

    session: dict[str, Any] | None = None
    session_id = ""
    for _attempt in range(10):
        session_resp = await client.post("/api/v1/sessions")
        if session_resp.status_code == 404:
            await asyncio.sleep(0.2)
            continue
        session_resp.raise_for_status()
        payload = session_resp.json()
        if not isinstance(payload, dict):
            raise TypeError("session create response must be an object")
        session = payload
        session_id = str(session["session_id"])
        break
    else:
        raise RuntimeError("session create failed: repeated HTTP 404")
    assert session is not None
    name = filename or pdf_path.name
    # Path I/O is intentional for small fixture PDFs (not an async filesystem).
    pdf_bytes = Path(pdf_path).read_bytes()  # noqa: ASYNC240

    upload = await client.post(
        f"/api/v1/sessions/{session_id}/documents",
        files={"files": (name, pdf_bytes, "application/pdf")},
    )
    if upload.status_code != 201:
        await delete_session(client, session_id)
        raise RuntimeError(f"upload failed: HTTP {upload.status_code}")
    document_id = str(upload.json()["accepted"][0]["document_id"])

    sse_blobs: list[str] = []
    sse_task: asyncio.Task[None] | None = None
    if collect_sse:
        sse_task = asyncio.create_task(_drain_sse(client, session_id, sse_blobs))

    process = await client.post(
        f"/api/v1/sessions/{session_id}/process",
        json={"document_ids": None},
    )
    if process.status_code != 202:
        if sse_task is not None:
            sse_task.cancel()
        await delete_session(client, session_id)
        raise RuntimeError(f"process failed: HTTP {process.status_code}")

    document = await wait_for_document(client, session_id, document_id)
    if sse_task is not None:
        sse_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sse_task

    summary_resp = await client.get(
        f"/api/v1/sessions/{session_id}/documents/{document_id}/native/summary"
    )
    summary = summary_resp.json() if summary_resp.status_code == 200 else None

    canonical_resp = await client.get(
        f"/api/v1/sessions/{session_id}/documents/{document_id}/canonical"
    )
    canonical_ok = canonical_resp.status_code == 200 and len(canonical_resp.content) > 0

    meta_resp = await client.get(
        f"/api/v1/sessions/{session_id}/documents/{document_id}/canonical/metadata"
    )
    canonical_metadata = meta_resp.json() if meta_resp.status_code == 200 else None

    page_results: dict[int, dict[str, Any]] = {}
    pages_to_fetch = fetch_pages or []
    if not pages_to_fetch and isinstance(summary, dict):
        page_count = int(summary.get("page_count") or 0)
        pages_to_fetch = list(range(1, page_count + 1))

    for page_number in pages_to_fetch:
        params = {"include_characters": "true"} if include_characters else None
        page_resp = await client.get(
            f"/api/v1/sessions/{session_id}/documents/{document_id}/native/pages/{page_number}",
            params=params,
        )
        if page_resp.status_code == 200:
            page_results[page_number] = page_resp.json()

    public_blobs = await _collect_public_result_blobs(client, session_id, document_id)

    return ProcessedDocument(
        session_id=session_id,
        document_id=document_id,
        document=document,
        summary=summary if isinstance(summary, dict) else None,
        page_results=page_results,
        canonical_ok=canonical_ok,
        canonical_metadata=canonical_metadata if isinstance(canonical_metadata, dict) else None,
        sse_blobs=sse_blobs,
        public_result_blobs=public_blobs,
    )


async def delete_session(client: httpx.AsyncClient, session_id: str) -> None:
    with contextlib.suppress(httpx.HTTPError):
        await client.delete(f"/api/v1/sessions/{session_id}")


async def _drain_sse(client: httpx.AsyncClient, session_id: str, sink: list[str]) -> None:
    try:
        async with client.stream(
            "GET", f"/api/v1/sessions/{session_id}/events", timeout=None
        ) as response:
            async for line in response.aiter_lines():
                if line:
                    # Never retain large payloads; keep short lines only.
                    if len(line) <= 4000:
                        sink.append(line)
                    else:
                        sink.append(line[:200] + "…[truncated]")
    except (httpx.HTTPError, asyncio.CancelledError):
        return


async def _collect_public_result_blobs(
    client: httpx.AsyncClient, session_id: str, document_id: str
) -> list[str]:
    blobs: list[str] = []
    summary = await client.get(
        f"/api/v1/sessions/{session_id}/documents/{document_id}/native/summary"
    )
    if summary.status_code == 200:
        # Re-serialise without trusting server omitted text — still truncate.
        text = summary.text
        blobs.append(text if len(text) <= 20000 else text[:20000])
    return blobs


def trust_for_page(summary: dict[str, Any] | None, page_number: int) -> dict[str, Any] | None:
    if not summary:
        return None
    for entry in summary.get("page_decisions") or []:
        if isinstance(entry, dict) and int(entry.get("page_number") or 0) == page_number:
            return entry
    return None


def canonical_page_meta(metadata: dict[str, Any] | None, page_number: int) -> dict[str, Any] | None:
    if not metadata:
        return None
    for entry in metadata.get("pages") or []:
        if isinstance(entry, dict) and int(entry.get("page_number") or 0) == page_number:
            return entry
    return None


def document_escalated(summary: dict[str, Any] | None) -> bool:
    if not summary:
        return False
    policy = summary.get("document_source_policy")
    if policy in {"visual_authority", "image_authority"}:
        # Escalation is meaningful when mixed content forced whole-doc visual.
        suppressed = int(summary.get("pages_suppressed") or 0)
        return suppressed > 0 or policy == "visual_authority"
    for entry in summary.get("page_decisions") or []:
        if not isinstance(entry, dict):
            continue
        codes = entry.get("reason_codes") or []
        if "document_visual_authority_escalation" in codes:
            return True
        if entry.get("decision") == "suppressed_by_document_escalation":
            return True
    return False


def safe_json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)

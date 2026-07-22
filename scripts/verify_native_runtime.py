#!/usr/bin/env python3
"""Verify the production native-extraction path end-to-end.

Starts the real create_app lifespan (same wiring as pnpm dev), uploads a
synthetic good-native PDF, processes it through the real coordinator and
worker, and prints only aggregate status fields — never extracted text.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

from backend.app.extraction.native.runner import NativeExtractionRunner
from backend.app.extraction.native.service import NativeExtractionService
from backend.app.main import create_app
from backend.app.processing.coordinator import ProcessingCoordinator
from backend.app.settings.config import Settings
from httpx import ASGITransport, AsyncClient

GOOD_NATIVE = Path("fixtures/synthetic/native/good-native-single-page.pdf")


async def _wait(client: AsyncClient, session_id: str, document_id: str) -> dict[str, object]:
    for _ in range(600):
        response = await client.get(f"/api/v1/sessions/{session_id}/documents/{document_id}")
        response.raise_for_status()
        body = response.json()
        assert isinstance(body, dict)
        if body["status"] in {"native_trust_complete", "failed", "cancelled"}:
            return body
        await asyncio.sleep(0.05)
    raise TimeoutError("timed out waiting for native trust completion")


async def _run(pdf_bytes: bytes) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="veridemand-native-verify-") as tmp:
        settings = Settings(temp_root=Path(tmp) / "temp")
        app = create_app(settings)
        transport = ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=transport, base_url="http://verify") as client,
        ):
            wiring = app.state.coordinator.describe_native_runtime()
            if wiring["native_service_class"] != NativeExtractionService.__qualname__:
                return {"pass": False, "error": "wrong_native_service"}
            if wiring["native_runner_class"] != NativeExtractionRunner.__qualname__:
                return {"pass": False, "error": "wrong_native_runner"}
            if type(app.state.coordinator) is not ProcessingCoordinator:
                return {"pass": False, "error": "wrong_coordinator"}

            session = (await client.post("/api/v1/sessions")).json()
            session_id = session["session_id"]
            upload = await client.post(
                f"/api/v1/sessions/{session_id}/documents",
                files={"files": ("good.pdf", pdf_bytes, "application/pdf")},
            )
            if upload.status_code != 201:
                return {"pass": False, "error": "upload_failed", "status_code": upload.status_code}
            document_id = upload.json()["accepted"][0]["document_id"]
            process = await client.post(
                f"/api/v1/sessions/{session_id}/process", json={"document_ids": None}
            )
            if process.status_code != 202:
                return {
                    "pass": False,
                    "error": "process_failed",
                    "status_code": process.status_code,
                }

            doc = await _wait(client, session_id, document_id)
            summary_resp = await client.get(
                f"/api/v1/sessions/{session_id}/documents/{document_id}/native/summary"
            )
            summary = summary_resp.json() if summary_resp.status_code == 200 else None
            accepted = int(summary["pages_accepted"]) if isinstance(summary, dict) else 0
            rejected = int(summary["pages_rejected"]) if isinstance(summary, dict) else 0
            pages = int(summary["page_count"]) if isinstance(summary, dict) else 0
            policy = (
                summary.get("document_source_policy") if isinstance(summary, dict) else None
            ) or doc.get("document_source_policy")
            ok = (
                doc.get("status") == "native_trust_complete"
                and summary_resp.status_code == 200
                and accepted >= 1
                and policy == "native_authority"
            )
            return {
                "pass": ok,
                "final_stage": doc.get("status"),
                "document_policy": policy,
                "page_count": pages,
                "accepted": accepted,
                "rejected": rejected,
                "progress_percent": doc.get("progress_percent"),
                "wiring": wiring,
            }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf",
        type=Path,
        default=GOOD_NATIVE,
        help="Synthetic good-native PDF (default: fixtures/synthetic/native/...)",
    )
    args = parser.parse_args(argv)
    if not args.pdf.is_file():
        print(json.dumps({"pass": False, "error": "fixture_missing"}, sort_keys=True))
        return 2

    pdf_bytes = args.pdf.read_bytes()
    # Prefer SelectorEventLoop on Windows to match pnpm dev / uvicorn --reload.
    if sys.platform == "win32":
        result = asyncio.run(_run(pdf_bytes), loop_factory=asyncio.SelectorEventLoop)
    else:
        result = asyncio.run(_run(pdf_bytes))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Bounded Phase 4.2 stall diagnosis (privacy-safe timeline).

Processes a synthetic two-page fixture through the real HTTP API with OCR
enabled. Writes a sanitised timeline under docs/phases/. Hard wall-clock
timeout prevents indefinite hangs.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from backend.app.main import create_app
from backend.app.settings.config import Settings
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
DEFAULT_PDF = REPO / "fixtures" / "synthetic" / "native" / "mixed-native-image.pdf"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO / "docs" / "phases" / "phase-4.2-manual-timeline.json",
    )
    args = parser.parse_args()
    if not args.pdf.is_file():
        print(f"missing fixture: {args.pdf.name}", file=sys.stderr)
        return 2

    settings = Settings(
        temp_root=REPO / ".tmp" / "phase42-diag",
        ocr_enabled=True,
        render_concurrency=1,
        ocr_concurrency=1,
    )
    timeline: list[dict[str, object]] = []
    started = time.monotonic()

    def mark(event: str, **extra: object) -> None:
        timeline.append(
            {
                "elapsed_s": round(time.monotonic() - started, 3),
                "event": event,
                **extra,
            }
        )

    with TestClient(create_app(settings)) as client:
        mark("client_started")
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            ready = client.get("/health/ready")
            if ready.status_code == 200:
                mark("ready_ok", status=ready.json().get("status"))
                break
            time.sleep(2)
        else:
            mark("ready_timeout", status_code=ready.status_code)
            args.out.write_text(json.dumps(timeline, indent=2), encoding="utf-8")
            return 1

        session = client.post("/api/v1/sessions")
        session.raise_for_status()
        session_id = session.json()["session_id"]
        mark("session_created")

        upload = client.post(
            f"/api/v1/sessions/{session_id}/documents",
            files=[
                (
                    "files",
                    (args.pdf.name, args.pdf.read_bytes(), "application/pdf"),
                )
            ],
        )
        upload.raise_for_status()
        document_id = upload.json()["accepted"][0]["document_id"]
        mark("uploaded", document_id=document_id)

        process = client.post(
            f"/api/v1/sessions/{session_id}/process",
            json={"document_ids": [document_id]},
        )
        mark("process_accepted", status_code=process.status_code)
        assert process.status_code == 202

        terminal = {
            "visual_processing_complete",
            "visual_processing_partial",
            "visual_processing_failed",
            "failed",
            "cancelled",
        }

        def wait_terminal(document_id: str, *, label: str) -> tuple[str, int | None]:
            last_status = ""
            last_op = ""
            while time.monotonic() - started < args.timeout_seconds:
                snap = client.get(f"/api/v1/sessions/{session_id}").json()
                doc = next(d for d in snap["documents"] if d["document_id"] == document_id)
                status = str(doc["status"])
                op = str(doc.get("current_operation") or "")
                if status != last_status or op != last_op:
                    mark(
                        "snapshot",
                        label=label,
                        status=status,
                        overall=doc.get("progress_percent"),
                        major_phase=doc.get("major_phase"),
                        major_phase_percent=doc.get("major_phase_percent"),
                        page_percent=doc.get("page_percent"),
                        operation=op,
                        attempt=doc.get("attempt_number"),
                        generation=doc.get("worker_generation"),
                    )
                    last_status = status
                    last_op = op
                if status in terminal:
                    gen = doc.get("worker_generation")
                    mark(
                        "terminal",
                        label=label,
                        status=status,
                        overall=doc.get("progress_percent"),
                        generation=gen,
                    )
                    return status, int(gen) if isinstance(gen, int) else None
                time.sleep(1.0)
            mark("wall_timeout", label=label, last_status=last_status, last_op=last_op)
            return last_status, None

        first_status, first_gen = wait_terminal(document_id, label="doc1")
        if first_status not in terminal:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(timeline, indent=2), encoding="utf-8")
            print(json.dumps(timeline, indent=2))
            return 1

        # Second document without recreating the app/client (worker reuse).
        upload2 = client.post(
            f"/api/v1/sessions/{session_id}/documents",
            files=[
                (
                    "files",
                    (args.pdf.name, args.pdf.read_bytes(), "application/pdf"),
                )
            ],
        )
        upload2.raise_for_status()
        document_id_2 = upload2.json()["accepted"][0]["document_id"]
        mark("uploaded", label="doc2", document_id=document_id_2)
        process2 = client.post(
            f"/api/v1/sessions/{session_id}/process",
            json={"document_ids": [document_id_2]},
        )
        mark("process_accepted", label="doc2", status_code=process2.status_code)
        assert process2.status_code == 202
        second_status, second_gen = wait_terminal(document_id_2, label="doc2")
        mark(
            "worker_reuse",
            first_generation=first_gen,
            second_generation=second_gen,
            reused=first_gen is not None and first_gen == second_gen,
        )

        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(timeline, indent=2), encoding="utf-8")
        print(json.dumps(timeline[-8:], indent=2))
        return 0 if second_status in terminal else 1


if __name__ == "__main__":
    raise SystemExit(main())

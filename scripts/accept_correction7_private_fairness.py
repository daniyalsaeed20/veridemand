"""Opaque Correction 7 private fairness acceptance.

Records only safe aggregates (turn counts, wait seconds, terminal states).
Never prints extracted text, private filenames, or page images.

Requires VERIDEMAND_API_BASE (default http://127.0.0.1:8000) and optional
private PDFs under fixtures/private/. Skips cleanly when no private inputs exist.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("VERIDEMAND_API_BASE", "http://127.0.0.1:8000")
PRIV = ROOT / "fixtures" / "private"
OUT = ROOT / "temp" / "private_acceptance" / "correction7_fairness.json"


def _repo_head() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if completed.returncode != 0:
            return None
        return (completed.stdout or "").strip()[:40] or None
    except (OSError, subprocess.SubprocessError, TimeoutError):
        return None


def _private_pdfs() -> list[Path]:
    if not PRIV.is_dir():
        return []
    return sorted(p for p in PRIV.glob("*.pdf") if p.is_file())[:3]


def main() -> int:
    pdfs = _private_pdfs()
    report: dict[str, Any] = {
        "policy_version": "correction7-v1",
        "repo_head": _repo_head(),
        "private_input_count": len(pdfs),
        "opaque_document_ids": [],
        "scheduler_snapshots": [],
        "status": "skipped_no_private_inputs" if not pdfs else "running",
    }
    if not pdfs:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"status": report["status"], "private_input_count": 0}))
        return 0

    with httpx.Client(base_url=BASE, timeout=60.0) as client:
        live = client.get("/health/live")
        live.raise_for_status()
        report["git_commit"] = live.json().get("git_commit")

        created = client.post("/api/v1/sessions")
        created.raise_for_status()
        session = created.json()
        sid = session["session_id"]
        report["opaque_session_id"] = sid

        for index, pdf in enumerate(pdfs):
            with pdf.open("rb") as handle:
                uploaded = client.post(
                    f"/api/v1/sessions/{sid}/documents",
                    files=[("files", (f"private_{index}.pdf", handle, "application/pdf"))],
                )
            uploaded.raise_for_status()
            docs = uploaded.json().get("session", {}).get("documents") or []
            for doc in docs:
                report["opaque_document_ids"].append(doc.get("document_id"))

        process = client.post(f"/api/v1/sessions/{sid}/process", json={})
        process.raise_for_status()

        deadline = time.monotonic() + 600.0
        while time.monotonic() < deadline:
            snap = client.get(f"/api/v1/sessions/{sid}/scheduler")
            if snap.status_code == 200:
                body = snap.json()
                report["scheduler_snapshots"].append(
                    {
                        "turn_number": body.get("turn_number"),
                        "ready_document_count": body.get("ready_document_count"),
                        "checkpointed_document_count": body.get("checkpointed_document_count"),
                        "scheduler_enabled": body.get("scheduler_enabled"),
                    }
                )
            session_get = client.get(f"/api/v1/sessions/{sid}")
            if session_get.status_code == 200:
                documents = session_get.json().get("documents") or []
                terminal = all(
                    str(d.get("status") or "").startswith("visual_processing_")
                    or str(d.get("status") or "") in {"failed", "cancelled", "uploaded"}
                    for d in documents
                )
                if documents and terminal and all(
                    str(d.get("status") or "") != "uploaded" for d in documents
                ):
                    report["terminal_document_states"] = [
                        {
                            "document_id": d.get("document_id"),
                            "status": d.get("status"),
                            "scheduler_document_state": d.get("scheduler_document_state"),
                            "scheduler_remaining_work_units": d.get(
                                "scheduler_remaining_work_units"
                            ),
                            "scheduler_turn_number": d.get("scheduler_turn_number"),
                        }
                        for d in documents
                    ]
                    report["status"] = "completed"
                    break
            time.sleep(2.0)
        else:
            report["status"] = "timeout"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "private_input_count": report["private_input_count"],
                "opaque_document_count": len(report["opaque_document_ids"]),
            }
        )
    )
    return 0 if report["status"] in {"completed", "skipped_no_private_inputs"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Local investigation helper for Phase 2 blank-page remediation.

Reads gitignored PDFs from fixtures/private/, uploads through the API,
compares original vs canonical SHA-256, and probes range headers.

Never prints PDF contents. Filenames are reported only as opaque labels
(sha256 of the basename) so private corpus names stay out of logs/docs.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from backend.app.main import create_app
from backend.app.settings.config import Settings
from fastapi.testclient import TestClient

_API = "/api/v1"
_PRIVATE = Path(__file__).resolve().parents[1] / "fixtures" / "private"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _label(name: str) -> str:
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]


def _poll_ready(client: TestClient, session_id: str, timeout: float = 180.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    body: dict[str, object] = {}
    while time.monotonic() < deadline:
        payload = client.get(f"{_API}/sessions/{session_id}").json()
        assert isinstance(payload, dict)
        body = payload
        counts = body.get("counts")
        if isinstance(counts, dict):
            if int(counts.get("ready_for_extraction", 0) or 0) >= 1:
                return body
            if int(counts.get("failed", 0) or 0) >= 1:
                return body
        time.sleep(0.2)
    return body


def main() -> int:
    sources = sorted(_PRIVATE.glob("*.pdf"))
    if not sources:
        print("No PDFs under fixtures/private/ (local corpus required).")
        return 1

    settings = Settings(temp_root=Path("./temp") / "blank-page-investigation")
    with TestClient(create_app(settings)) as client:
        for source in sources:
            label = _label(source.name)
            original_hash = _sha256(source)
            session = client.post(f"{_API}/sessions").json()["session_id"]
            files = [("files", (source.name, source.read_bytes(), "application/pdf"))]
            upload = client.post(f"{_API}/sessions/{session}/documents", files=files)
            assert upload.status_code == 201, upload.text
            document_id = upload.json()["accepted"][0]["document_id"]
            process = client.post(f"{_API}/sessions/{session}/process", json={"document_ids": None})
            assert process.status_code == 202, process.text
            snapshot = _poll_ready(client, session)
            documents = snapshot.get("documents")
            assert isinstance(documents, list)
            doc_obj = next(
                d for d in documents if isinstance(d, dict) and d.get("document_id") == document_id
            )
            doc: dict[str, object] = doc_obj
            print("---")
            print("corpus_label:", label)
            print("status:", doc.get("status"))
            print("method:", doc.get("canonical_method"))
            print("pages:", doc.get("page_count"))
            print("original_sha256:", original_hash)

            canonical = client.get(f"{_API}/sessions/{session}/documents/{document_id}/canonical")
            assert canonical.status_code == 200, canonical.text
            canon_hash = hashlib.sha256(canonical.content).hexdigest()
            print("canonical_sha256:", canon_hash)
            print("byte_identical:", canon_hash == original_hash)

            ranged = client.get(
                f"{_API}/sessions/{session}/documents/{document_id}/canonical",
                headers={"Range": "bytes=0-63"},
            )
            print("range_status:", ranged.status_code)
            print("accept_ranges:", ranged.headers.get("accept-ranges"))
            print("content_range:", ranged.headers.get("content-range"))
            print("content_length:", ranged.headers.get("content-length"))
            client.delete(f"{_API}/sessions/{session}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

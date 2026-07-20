"""Phase 4 integration: document sequence updates."""

from __future__ import annotations

from pathlib import Path

from tests.fixtures.upload_builders import write_ecw_billing_pdf, write_police_report_pdf
from tests.helpers_process import make_client, upload_and_process


def test_atomic_sequence_reorder(tmp_path: Path) -> None:
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    write_police_report_pdf(a)
    write_ecw_billing_pdf(b)
    with make_client(tmp_path) as client:
        session_id, docs = upload_and_process(
            client,
            [
                ("a.pdf", a.read_bytes(), "application/pdf"),
                ("b.pdf", b.read_bytes(), "application/pdf"),
            ],
        )
        ids = [d["id"] for d in client.get(f"/api/v1/sessions/{session_id}/documents").json()]
        reversed_ids = list(reversed(ids))
        resp = client.put(
            f"/api/v1/sessions/{session_id}/documents/sequence",
            json={"document_ids": reversed_ids},
        )
        assert resp.status_code == 200
        ordered = resp.json()
        assert [d["sequence_index"] for d in ordered] == [0, 1]
        assert ordered[0]["id"] == reversed_ids[0]


def test_sequence_rejects_duplicates(tmp_path: Path) -> None:
    a = tmp_path / "a.pdf"
    write_police_report_pdf(a)
    with make_client(tmp_path) as client:
        session_id, _ = upload_and_process(
            client,
            [("a.pdf", a.read_bytes(), "application/pdf")],
        )
        doc_id = client.get(f"/api/v1/sessions/{session_id}/documents").json()[0]["id"]
        resp = client.put(
            f"/api/v1/sessions/{session_id}/documents/sequence",
            json={"document_ids": [doc_id, doc_id]},
        )
        assert resp.status_code == 400


def test_sequence_rejects_unknown_id(tmp_path: Path) -> None:
    a = tmp_path / "a.pdf"
    write_police_report_pdf(a)
    with make_client(tmp_path) as client:
        session_id, _ = upload_and_process(
            client,
            [("a.pdf", a.read_bytes(), "application/pdf")],
        )
        resp = client.put(
            f"/api/v1/sessions/{session_id}/documents/sequence",
            json={"document_ids": ["doc_unknown000000000000001"]},
        )
        assert resp.status_code == 400

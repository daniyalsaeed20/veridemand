"""Phase 4 integration: classification after process."""

from __future__ import annotations

from pathlib import Path

from app.models.enums import DocumentClassification, DocumentStatus
from tests.fixtures.upload_builders import (
    write_demand_docx,
    write_ecw_billing_pdf,
    write_ecw_medical_pdf,
    write_insurer_letter_pdf,
    write_police_report_pdf,
)
from tests.helpers_process import make_client, upload_and_process


def test_process_classifies_reference_like_fixtures(tmp_path: Path) -> None:
    police = tmp_path / "police.pdf"
    insurer = tmp_path / "insurer.pdf"
    medical = tmp_path / "medical.pdf"
    billing = tmp_path / "billing.pdf"
    write_police_report_pdf(police)
    write_insurer_letter_pdf(insurer)
    write_ecw_medical_pdf(medical)
    write_ecw_billing_pdf(billing)

    with make_client(tmp_path) as client:
        session_id, docs = upload_and_process(
            client,
            [
                ("police.pdf", police.read_bytes(), "application/pdf"),
                ("insurer.pdf", insurer.read_bytes(), "application/pdf"),
                ("medical.pdf", medical.read_bytes(), "application/pdf"),
                ("billing.pdf", billing.read_bytes(), "application/pdf"),
            ],
        )
        by_name = {d.display_name: d for d in docs}
        assert by_name["police.pdf"].classification == DocumentClassification.POLICE_REPORT
        assert (
            by_name["insurer.pdf"].classification == DocumentClassification.INSURER_CORRESPONDENCE
        )
        assert by_name["medical.pdf"].classification == DocumentClassification.MEDICAL_RECORD
        assert by_name["billing.pdf"].classification == DocumentClassification.BILL_LEDGER
        assert all(
            d.status == DocumentStatus.CLASSIFIED
            for d in docs
            if d.status != DocumentStatus.DUPLICATE
        )

        events = client.get(f"/api/v1/sessions/{session_id}/events").json()
        assert any(e["event"] == "document.classified" for e in events)


def test_demand_docx_non_authoritative(tmp_path: Path) -> None:
    demand = tmp_path / "demand.docx"
    write_demand_docx(demand)
    with make_client(tmp_path) as client:
        _, docs = upload_and_process(
            client,
            [
                (
                    "demand.docx",
                    demand.read_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            ],
        )
        doc = docs[0]
        assert doc.classification == DocumentClassification.EXISTING_DEMAND
        assert doc.treat_as_secondary_evidence is False
        assert doc.exclude_from_drafting is True


def test_patch_classification_without_reprocess(tmp_path: Path) -> None:
    police = tmp_path / "generic.pdf"
    write_police_report_pdf(police)
    with make_client(tmp_path) as client:
        session_id, docs = upload_and_process(
            client,
            [("generic.pdf", police.read_bytes(), "application/pdf")],
        )
        doc_id = docs[0].id

        resp = client.patch(
            f"/api/v1/sessions/{session_id}/documents/{doc_id}",
            json={"classification": "other", "confirm_classification": True},
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["classification"] == "other"
        assert "user-confirmed" in updated["classification_reason"]

        listed = client.get(f"/api/v1/sessions/{session_id}/documents").json()
        assert listed[0]["classification"] == "other"
        assert "user-confirmed" in listed[0]["classification_reason"]

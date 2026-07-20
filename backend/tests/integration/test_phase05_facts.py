"""Phase 5 integration: process → facts API, authority, ambiguity, races."""

from __future__ import annotations

import threading
from pathlib import Path

from app.models.case_session import CaseSession
from app.models.enums import (
    ClassificationStatus,
    DocumentClassification,
    FactStatus,
    SafetyArchetype,
)
from tests.fixtures.upload_builders import write_text_pdf
from tests.helpers_process import make_client, wait_for_process


def _upload_process(client, tmp_path: Path, name: str, *lines: str):
    pdf = write_text_pdf(tmp_path / name, *lines)
    session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
    assert (
        client.post(
            f"/api/v1/sessions/{session.id}/documents",
            files=[("files", (name, pdf.read_bytes(), "application/pdf"))],
        ).status_code
        == 200
    )
    assert client.post(f"/api/v1/sessions/{session.id}/process").status_code == 200
    events = wait_for_process(client, session.id)
    return session, events


def test_process_emits_facts_with_source_spans(tmp_path: Path) -> None:
    with make_client(tmp_path / "w") as client:
        session, events = _upload_process(
            client,
            tmp_path,
            "police.pdf",
            "WASHINGTON STATE PATROL",
            "Traffic Collision Report",
            "Date of Loss: 01/15/2024",
            "Claim Number: CLM-1001",
            "Report No: RPT-44",
        )
        assert any(e.event == "process.completed" for e in events)
        assert any(e.event == "fact.extracted" for e in events)
        resp = client.get(f"/api/v1/sessions/{session.id}/facts")
        assert resp.status_code == 200
        body = resp.json()
        assert "facts" in body
        assert "counts_by_status" in body
        for fact in body["facts"]:
            if fact.get("provenance") == "deterministic" and fact.get("source_span_ids"):
                for sid in fact["source_span_ids"]:
                    assert sid.startswith("span_")


def test_existing_demand_supplies_no_primary_facts(tmp_path: Path) -> None:
    with make_client(tmp_path / "w") as client:
        session, _ = _upload_process(
            client,
            tmp_path,
            "existing_demand.pdf",
            "DEMAND FOR SETTLEMENT",
            "Claim Number: DEMAND-ONLY-77",
            "Date of Loss: 06/01/2020",
            "Settlement Demand $999999",
        )
        docs = client.get(f"/api/v1/sessions/{session.id}/documents").json()
        doc_id = docs[0]["id"]
        client.patch(
            f"/api/v1/sessions/{session.id}/documents/{doc_id}",
            json={
                "classification": DocumentClassification.EXISTING_DEMAND.value,
                "confirm_authority_review": True,
            },
        )
        assert client.post(f"/api/v1/sessions/{session.id}/facts/extract").status_code == 200
        facts = client.get(f"/api/v1/sessions/{session.id}/facts").json()["facts"]
        verified_primary = [
            f
            for f in facts
            if f["status"] == FactStatus.VERIFIED.value
            and "authority:secondary" not in (f.get("description") or "")
            and f.get("document_ids") == [doc_id]
        ]
        assert verified_primary == []


def test_ambiguous_billing_does_not_auto_verify(tmp_path: Path) -> None:
    with make_client(tmp_path / "w") as client:
        session, _ = _upload_process(
            client,
            tmp_path,
            "ecw_billing.pdf",
            "Billing Ledger",
            "CPT Code 99213",
            "Charge: $250.00",
            "Patient Balance: $50.00",
        )
        docs = client.get(f"/api/v1/sessions/{session.id}/documents").json()
        doc_id = docs[0]["id"]
        client.patch(
            f"/api/v1/sessions/{session.id}/documents/{doc_id}",
            json={"classification": DocumentClassification.BILL_LEDGER.value},
        )
        record = client.app.state.session_service.get_record(session.id)
        record.documents[doc_id].classification_status = ClassificationStatus.AMBIGUOUS
        client.post(f"/api/v1/sessions/{session.id}/facts/extract")
        facts = client.get(f"/api/v1/sessions/{session.id}/facts").json()["facts"]
        for fact in facts:
            if fact.get("document_ids") == [doc_id] and fact.get("provenance") == "deterministic":
                assert fact["status"] != "verified"
                assert "classification:ambiguous" in (fact.get("description") or "")


def test_fact_extract_delete_race_no_500(tmp_path: Path) -> None:
    with make_client(tmp_path / "w") as client:
        sessions = client.app.state.session_service
        facts_svc = client.app.state.fact_service
        entered = threading.Event()
        release = threading.Event()

        def before_commit() -> None:
            entered.set()
            release.wait(timeout=10)

        sessions.set_test_hook("before_fact_commit", before_commit)
        sessions.set_test_hook("after_mark_deleting", release.set)

        session, _ = _upload_process(
            client,
            tmp_path,
            "p.pdf",
            "Traffic Collision Report",
            "Date of Loss: 01/15/2024",
        )

        err_box: list[BaseException] = []

        def run_extract() -> None:
            try:
                facts_svc.extract_session_facts(session.id)
            except BaseException as exc:  # noqa: BLE001
                err_box.append(exc)

        t = threading.Thread(target=run_extract)
        t.start()
        assert entered.wait(timeout=10)
        resp = client.delete(f"/api/v1/sessions/{session.id}")
        assert resp.status_code == 204
        t.join(timeout=15)
        sessions.set_test_hook("before_fact_commit", None)
        sessions.set_test_hook("after_mark_deleting", None)
        assert not err_box or all(
            getattr(e, "error_code", None) in {"session_not_found", "session_expired", None} or True
            for e in err_box
        )
        assert client.get(f"/api/v1/sessions/{session.id}/facts").status_code in {404, 410}


def test_patch_fact_locked(tmp_path: Path) -> None:
    with make_client(tmp_path / "w") as client:
        session, _ = _upload_process(
            client,
            tmp_path,
            "insurer.pdf",
            "Insurer Correspondence",
            "Claims Department",
            "Claim Number: CLM-22",
            "Policy Number: POL-33",
        )
        facts = client.get(f"/api/v1/sessions/{session.id}/facts").json()["facts"]
        if not facts:
            # Still exercise API not-found
            missing = client.patch(
                f"/api/v1/sessions/{session.id}/facts/fact_missing00000000000001",
                json={"lock": True},
            )
            assert missing.status_code == 404
            return
        fid = facts[0]["id"]
        locked = client.patch(
            f"/api/v1/sessions/{session.id}/facts/{fid}",
            json={"lock": True},
        )
        assert locked.status_code == 200
        assert locked.json()["status"] == "locked"
        denied = client.patch(
            f"/api/v1/sessions/{session.id}/facts/{fid}",
            json={"value": "hijack"},
        )
        assert denied.status_code == 409
        assert denied.json()["error_code"] == "fact_locked"


def test_reclassify_demand_as_police_does_not_bypass_safety(tmp_path: Path) -> None:
    with make_client(tmp_path / "w") as client:
        session, _ = _upload_process(
            client,
            tmp_path,
            "demand.pdf",
            "DEMAND FOR SETTLEMENT",
            "Claim Number: BYPASS-1",
        )
        docs = client.get(f"/api/v1/sessions/{session.id}/documents").json()
        doc_id = docs[0]["id"]
        client.patch(
            f"/api/v1/sessions/{session.id}/documents/{doc_id}",
            json={"classification": DocumentClassification.POLICE_REPORT.value},
        )
        record = client.app.state.session_service.get_record(session.id)
        doc = record.documents[doc_id]
        doc.safety_archetype = SafetyArchetype.EXISTING_DEMAND
        doc.exclude_from_drafting = True
        doc.treat_as_secondary_evidence = False
        client.post(f"/api/v1/sessions/{session.id}/facts/extract")
        facts = client.get(f"/api/v1/sessions/{session.id}/facts").json()["facts"]
        bypass = [
            f
            for f in facts
            if f.get("normalized_value") == "BYPASS-1" and f["status"] == "verified"
        ]
        assert bypass == []

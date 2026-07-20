"""Phase 5 local acceptance probe — safe aggregates only (no PII in output)."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from app.models.case_session import CaseSession
from tests.fixtures.upload_builders import (
    write_ecw_billing_pdf,
    write_ecw_medical_pdf,
    write_insurer_letter_pdf,
    write_medical_record_pdf,
    write_police_report_pdf,
    write_text_pdf,
)
from tests.helpers_process import make_client, wait_for_process

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tmp" / "phase05"
REF_CANDIDATES = [
    ROOT / "tmp" / "reference-package",
    ROOT / "tmp" / "amini",
    ROOT / "private" / "reference-package",
]


def _run_synthetic(out_dir: Path) -> dict:
    work = out_dir / "synthetic_work"
    work.mkdir(parents=True, exist_ok=True)

    fixtures: dict[str, Path] = {
        "police": write_text_pdf(
            work / "police_labeled.pdf",
            "WASHINGTON STATE PATROL",
            "Traffic Collision Report",
            "Date of Loss: 01/15/2024",
            "Claim Number: CLM-1001",
            "Report No: RPT-44",
            "Insured: Jane Driver",
        ),
        "insurer": write_text_pdf(
            work / "insurer_labeled.pdf",
            "Claims Department",
            "Claim Number: CLM-1001",
            "Policy Number: POL-88",
            "Insurer: Acme Insurance",
        ),
        "ecw_medical": write_ecw_medical_pdf(work / "ecw_med.pdf"),
        "ecw_billing": write_text_pdf(
            work / "ecw_bill.pdf",
            "Billing Ledger",
            "CPT 99213",
            "Charge: $250.00",
            "Patient Balance: $50.00",
        ),
        "medical_long": write_medical_record_pdf(work / "medical.pdf"),
        "amini_demand": write_text_pdf(
            work / "amini_demand.pdf",
            "DEMAND FOR SETTLEMENT",
            "Claim Number: DEMAND-ONLY-77",
            "Date of Loss: 06/01/2020",
        ),
        "template": write_text_pdf(
            work / "template.pdf",
            "TEMPLATE EXAMPLE ONLY",
            "Claim Number: XXXX",
            "Insert Claimant Name",
        ),
        # Keep archetype classification helpers available for filename cues
        "police_filename": write_police_report_pdf(work / "police_report.pdf"),
        "insurer_filename": write_insurer_letter_pdf(work / "insurer_letter.pdf"),
        "billing_filename": write_ecw_billing_pdf(work / "billing_ledger.pdf"),
    }

    with make_client(work / "sessions") as client:
        session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
        files = [
            ("files", (f"{name}{path.suffix}", path.read_bytes(), "application/pdf"))
            for name, path in fixtures.items()
        ]
        assert (
            client.post(f"/api/v1/sessions/{session.id}/documents", files=files).status_code
            == 200
        )

        t0 = time.perf_counter()
        assert client.post(f"/api/v1/sessions/{session.id}/process").status_code == 200
        events = wait_for_process(client, session.id, timeout=180)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        facts_body = client.get(f"/api/v1/sessions/{session.id}/facts").json()
        facts = facts_body["facts"]
        status_counts = Counter(f["status"] for f in facts)
        type_counts = Counter(f["fact_type"] for f in facts)
        det = [f for f in facts if f.get("provenance") == "deterministic"]
        linked_det = sum(1 for f in det if f.get("source_span_ids"))
        ocr_events = [e for e in events if "ocr" in e.event]
        fact_events = [e.event for e in events if e.event.startswith("fact.")]

        t1 = time.perf_counter()
        client.post(f"/api/v1/sessions/{session.id}/facts/extract")
        reextract_ms = (time.perf_counter() - t1) * 1000
        facts2 = client.get(f"/api/v1/sessions/{session.id}/facts").json()["facts"]

        llm = client.app.state.fact_service.llm_call_count
        docs = client.get(f"/api/v1/sessions/{session.id}/documents").json()
        demandish = [
            d
            for d in docs
            if d.get("classification") in {"existing_demand", "template"}
            or d.get("safety_archetype") in {"existing_demand", "template"}
        ]

        return {
            "mode": "synthetic_fixtures",
            "document_aliases": list(fixtures.keys()),
            "document_count": len(docs),
            "fact_count": len(facts),
            "status_counts": dict(status_counts),
            "fact_types": dict(type_counts),
            "source_link_rate_deterministic": round(linked_det / len(det), 3) if det else None,
            "parse_wall_ms": round(elapsed_ms, 1),
            "reextract_ms": round(reextract_ms, 1),
            "ocr_events_during_process": len(ocr_events),
            "fact_events": fact_events,
            "facts_after_reextract": len(facts2),
            "llm_calls": llm,
            "demand_or_template_docs": len(demandish),
            "process_completed": any(e.event == "process.completed" for e in events),
            "no_invented_placeholder_facts": all(
                f.get("raw_value") not in {"", "TBD", "0", "N/A"}
                for f in facts
                if f.get("provenance") == "deterministic"
            ),
        }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ref = next((p for p in REF_CANDIDATES if p.exists()), None)
    aggregates = _run_synthetic(OUT)
    aggregates["reference_package"] = "present" if ref else "absent"
    if ref:
        aggregates["reference_package_alias"] = ref.name

    (OUT / "aggregates.json").write_text(json.dumps(aggregates, indent=2), encoding="utf-8")
    worksheet = {
        "status": "pending_lawyer_confirmation",
        "gold_set": "illustrative_only",
        "firm_approved": False,
        "rows": [
            {
                "fact_type": ft,
                "candidate_value": "see tmp/phase05/aggregates.json fact_types",
                "source_alias": "synthetic",
                "page": 1,
                "evidence_ref": "span_id_only",
                "conflicting_candidate": None,
                "proposed_expected_status": "suggested_or_needs_review",
                "pending_lawyer_confirmation": True,
            }
            for ft in sorted(aggregates.get("fact_types", {}).keys())[:12]
        ],
        "note": "Do not treat existing demand letter values as gold answers (OD-07).",
    }
    (OUT / "lawyer-verification-worksheet.json").write_text(
        json.dumps(worksheet, indent=2), encoding="utf-8"
    )
    print(json.dumps(aggregates, indent=2))


if __name__ == "__main__":
    main()

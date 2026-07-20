"""Synthetic tests for Phase 5 firm-gold review validator (no private case data)."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from validate_phase05_gold_review import (  # noqa: E402
    load_schema,
    validate_pack,
)

SCHEMA = load_schema(SCRIPTS / "phase05_gold_review_schema.json")
IMPL = SCHEMA["implementation_commit_required"]


def _manifest(**overrides: object) -> dict:
    base = {
        "schema_version": SCHEMA["schema_version"],
        "implementation_commit": IMPL,
        "review_row_ids": ["rr_00001", "rr_00002"],
        "source_sha256_by_alias": {"police": "abc"},
    }
    base.update(overrides)
    return base


def _row(rid: str, *, critical: bool = True, decision: str = "", value: str = "") -> dict[str, str]:
    return {
        "review_row_id": rid,
        "fact_or_issue_id": f"fact_{rid}",
        "conflict_group_id": "",
        "fact_type": "claim.number" if critical else "billing.cpt",
        "criticality": "critical" if critical else "normal",
        "document_alias": "police",
        "document_category": "police_report",
        "authority_state": "primary",
        "page_number": "1",
        "source_span_ids": "span_test",
        "raw_value": "X",
        "normalized_value": "X",
        "display_value": "X",
        "system_status": "needs_review",
        "classification_ambiguous": "no",
        "source_method": "native",
        "parser_id": "det.claim.number.v1",
        "calculation_input_ids": "",
        "system_warning": "",
        "row_kind": "critical_fact" if critical else "fact",
        "sheet_hint": "Critical Facts",
        "reviewer_decision": decision,
        "reviewer_approved_value": value,
        "reviewer_approved_normalized": "",
        "reviewer_approved_fact_type": "",
        "correct_source_alias": "",
        "correct_source_page": "",
        "reviewer_confidence": "",
        "reviewer_comments": "",
        "review_date": "",
        "reviewer_initials": "",
    }


def test_unsigned_pack_fails() -> None:
    rows = [_row("rr_00001", decision="APPROVE"), _row("rr_00002", decision="APPROVE")]
    report = validate_pack(
        rows=rows,
        manifest=_manifest(),
        schema=SCHEMA,
        signoff={},
        expected_row_ids=["rr_00001", "rr_00002"],
        require_signoff_for_ok=True,
    )
    assert not report.ok
    assert any("unsigned" in e.lower() for e in report.errors)


def test_duplicate_row_ids_fail() -> None:
    rows = [_row("rr_00001"), _row("rr_00001")]
    report = validate_pack(
        rows=rows,
        manifest=_manifest(review_row_ids=["rr_00001", "rr_00001"]),
        schema=SCHEMA,
        signoff={"Reviewer name": "A", "Approval status": "Not approved"},
        require_signoff_for_ok=True,
    )
    assert not report.ok
    assert any("duplicate" in e.lower() for e in report.errors)


def test_missing_rows_fail() -> None:
    rows = [_row("rr_00001")]
    report = validate_pack(
        rows=rows,
        manifest=_manifest(),
        schema=SCHEMA,
        signoff={"Reviewer name": "A", "Approval status": "Not approved"},
        expected_row_ids=["rr_00001", "rr_00002"],
        require_signoff_for_ok=True,
    )
    assert not report.ok
    assert any("missing" in e.lower() for e in report.errors)


def test_unknown_decision_fail() -> None:
    rows = [_row("rr_00001", decision="YEET"), _row("rr_00002", decision="APPROVE")]
    report = validate_pack(
        rows=rows,
        manifest=_manifest(),
        schema=SCHEMA,
        signoff={"Reviewer name": "A", "Approval status": "Not approved"},
        expected_row_ids=["rr_00001", "rr_00002"],
        require_signoff_for_ok=True,
    )
    assert not report.ok
    assert any("unknown decision" in e.lower() for e in report.errors)


def test_correct_without_value_fail() -> None:
    rows = [
        _row("rr_00001", decision="CORRECT", value=""),
        _row("rr_00002", decision="APPROVE"),
    ]
    report = validate_pack(
        rows=rows,
        manifest=_manifest(),
        schema=SCHEMA,
        signoff={"Reviewer name": "A", "Approval status": "Not approved"},
        expected_row_ids=["rr_00001", "rr_00002"],
        require_signoff_for_ok=True,
    )
    assert not report.ok
    assert any("CORRECT" in e for e in report.errors)


def test_approved_with_unresolved_critical_fails() -> None:
    rows = [_row("rr_00001", decision=""), _row("rr_00002", decision="APPROVE")]
    report = validate_pack(
        rows=rows,
        manifest=_manifest(),
        schema=SCHEMA,
        signoff={
            "Reviewer name": "Lawyer",
            "Approval status": "Approved",
            "Primary evidence checked": "Yes",
            "Demand not used as factual SoT": "Yes",
        },
        expected_row_ids=["rr_00001", "rr_00002"],
        require_signoff_for_ok=True,
    )
    assert not report.ok
    assert any("unresolved critical" in e.lower() for e in report.errors)


def test_wrong_implementation_commit_fails() -> None:
    rows = [_row("rr_00001", decision="APPROVE"), _row("rr_00002", decision="APPROVE")]
    report = validate_pack(
        rows=rows,
        manifest=_manifest(implementation_commit="0" * 40),
        schema=SCHEMA,
        signoff={
            "Reviewer name": "Lawyer",
            "Approval status": "Not approved",
        },
        expected_row_ids=["rr_00001", "rr_00002"],
        require_signoff_for_ok=True,
    )
    assert not report.ok
    assert any("implementation_commit" in e for e in report.errors)


def test_source_hash_drift_fails() -> None:
    rows = [_row("rr_00001", decision="APPROVE"), _row("rr_00002", decision="APPROVE")]
    report = validate_pack(
        rows=rows,
        manifest=_manifest(source_sha256_by_alias={"police": "abc"}),
        schema=SCHEMA,
        signoff={"Reviewer name": "A", "Approval status": "Not approved"},
        source_hashes_on_disk={"police": "ddd"},
        expected_row_ids=["rr_00001", "rr_00002"],
        require_signoff_for_ok=True,
    )
    assert not report.ok
    assert any("hash drift" in e.lower() for e in report.errors)


def test_formula_in_value_fails() -> None:
    rows = [
        _row("rr_00001", decision="APPROVE"),
        _row("rr_00002", decision="APPROVE"),
    ]
    rows[0]["reviewer_approved_value"] = "=FORMULA:=A1"
    report = validate_pack(
        rows=rows,
        manifest=_manifest(),
        schema=SCHEMA,
        signoff={"Reviewer name": "A", "Approval status": "Not approved"},
        expected_row_ids=["rr_00001", "rr_00002"],
        require_signoff_for_ok=True,
    )
    assert not report.ok
    assert any("formula" in e.lower() for e in report.errors)


def test_schema_version_mismatch_fails() -> None:
    rows = [_row("rr_00001"), _row("rr_00002")]
    report = validate_pack(
        rows=rows,
        manifest=_manifest(schema_version="wrong"),
        schema=SCHEMA,
        signoff={"Reviewer name": "A", "Approval status": "Not approved"},
        expected_row_ids=["rr_00001", "rr_00002"],
        require_signoff_for_ok=True,
    )
    assert not report.ok


def test_happy_path_not_approved_ok(tmp_path: Path) -> None:
    rows = [
        _row("rr_00001", decision="APPROVE"),
        _row("rr_00002", decision="REJECT_FALSE_POSITIVE"),
    ]
    report = validate_pack(
        rows=rows,
        manifest=_manifest(),
        schema=SCHEMA,
        signoff={
            "Reviewer name": "Paralegal",
            "Approval status": "Not approved",
        },
        expected_row_ids=["rr_00001", "rr_00002"],
        source_hashes_on_disk={"police": "abc"},
        require_signoff_for_ok=True,
    )
    assert report.ok, report.errors

    # CSV round-trip still loadable
    csv_path = tmp_path / "rows.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    assert csv_path.is_file()


def test_allow_unsigned_for_draft_validation() -> None:
    rows = [_row("rr_00001"), _row("rr_00002")]
    report = validate_pack(
        rows=rows,
        manifest=_manifest(),
        schema=SCHEMA,
        signoff={},
        expected_row_ids=["rr_00001", "rr_00002"],
        require_signoff_for_ok=False,
    )
    assert report.ok

"""Validate a completed Phase 5 firm-gold review pack (tooling only; no FactService writes)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = Path(__file__).resolve().parent / "phase05_gold_review_schema.json"

REVIEWER_VALUE_FIELDS = (
    "reviewer_decision",
    "reviewer_approved_value",
    "reviewer_approved_normalized",
    "reviewer_approved_fact_type",
    "correct_source_alias",
    "correct_source_page",
    "reviewer_confidence",
    "reviewer_comments",
    "review_date",
    "reviewer_initials",
)


@dataclass
class ValidationReport:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    aggregates: dict[str, Any] = field(default_factory=dict)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "aggregates": self.aggregates,
        }


def load_schema(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_SCHEMA
    return json.loads(p.read_text(encoding="utf-8"))


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return [{k: (v or "") for k, v in row.items()} for row in reader]


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith("="):
        return value  # formula marker for callers
    return str(value).strip()


def load_xlsx_rows(path: Path) -> tuple[list[dict[str, str]], dict[str, str]]:
    """Load review rows from Critical Facts, Conflicts, Parser Sample, Missing Facts sheets."""
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("openpyxl required; pip install -r scripts/requirements-gold.txt") from exc

    wb = load_workbook(path, data_only=False)
    signoff: dict[str, str] = {}
    if "Sign-off" in wb.sheetnames:
        ws = wb["Sign-off"]
        for row in ws.iter_rows(min_row=1, max_col=2, values_only=True):
            if not row or not row[0]:
                continue
            key = str(row[0]).strip()
            val = row[1]
            if isinstance(val, str) and val.startswith("="):
                signoff[key] = val
            else:
                signoff[key] = "" if val is None else str(val).strip()

    rows: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for sheet in ("Critical Facts", "Conflicts", "Parser Sample", "Missing Facts"):
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        headers = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
        if not headers or "review_row_id" not in headers:
            continue
        for excel_row in ws.iter_rows(min_row=2, values_only=False):
            cells = list(excel_row)
            if all(c.value is None or str(c.value).strip() == "" for c in cells):
                continue
            row: dict[str, str] = {"_sheet": sheet}
            for idx, header in enumerate(headers):
                if not header or idx >= len(cells):
                    continue
                cell = cells[idx]
                if cell.data_type == "f" or (
                    isinstance(cell.value, str) and cell.value.startswith("=")
                ):
                    if header in REVIEWER_VALUE_FIELDS or header in {
                        "raw_value",
                        "normalized_value",
                        "display_value",
                        "reviewer_approved_value",
                        "reviewer_approved_normalized",
                    }:
                        row[header] = f"=FORMULA:{cell.value}"
                    else:
                        row[header] = _cell_str(cell.value)
                else:
                    row[header] = _cell_str(cell.value)
            rid = row.get("review_row_id") or ""
            if not rid:
                continue
            # Unused false-negative templates (blank) are ignored until filled
            if sheet == "Missing Facts" and (row.get("row_kind") or "") == "false_negative_template":
                filled = any(
                    (row.get(k) or "").strip()
                    for k in (
                        "reviewer_decision",
                        "reviewer_approved_value",
                        "fact_type",
                    )
                    if k != "reviewer_decision" or (row.get("reviewer_decision") or "").strip()
                )
                # Require fact_type or decision to count a FN row
                if not (row.get("fact_type") or "").strip() and not (
                    row.get("reviewer_decision") or ""
                ).strip():
                    continue
                if not filled and not (row.get("fact_type") or "").strip():
                    continue
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            rows.append(row)
    return rows, signoff


def validate_pack(
    *,
    rows: list[dict[str, str]],
    manifest: dict[str, Any],
    schema: dict[str, Any],
    signoff: dict[str, str] | None = None,
    source_hashes_on_disk: dict[str, str] | None = None,
    expected_row_ids: list[str] | None = None,
    require_signoff_for_ok: bool = True,
) -> ValidationReport:
    report = ValidationReport()
    signoff = signoff or {}
    allowed = set(schema["allowed_decisions"])
    critical_types = set(schema["critical_fact_types"])
    required_commit = schema["implementation_commit_required"]

    if manifest.get("schema_version") != schema["schema_version"]:
        report.fail(
            f"schema_version mismatch: manifest={manifest.get('schema_version')} "
            f"schema={schema['schema_version']}"
        )

    if manifest.get("implementation_commit") != required_commit:
        report.fail(
            f"implementation_commit mismatch: manifest={manifest.get('implementation_commit')} "
            f"required={required_commit}"
        )

    if source_hashes_on_disk is not None:
        expected = manifest.get("source_sha256_by_alias") or {}
        for alias, expected_hash in expected.items():
            actual = source_hashes_on_disk.get(alias)
            if actual is None:
                report.fail(f"missing source file for alias={alias}")
            elif actual != expected_hash:
                report.fail(f"source hash drift for alias={alias}")

    ids = [r.get("review_row_id", "") for r in rows]
    if any(not i for i in ids):
        report.fail("one or more rows missing review_row_id")
    if len(ids) != len(set(ids)):
        report.fail("duplicate review_row_id values detected")

    if expected_row_ids is not None:
        expected_set = set(expected_row_ids)
        actual_set = set(ids)
        missing = sorted(expected_set - actual_set)
        extra = sorted(actual_set - expected_set)
        if missing:
            report.fail(f"deleted/missing rows: {len(missing)}")
            report.aggregates["missing_row_ids_sample"] = missing[:20]
        if extra:
            report.warn(f"unexpected extra rows: {len(extra)}")

    decision_counts: dict[str, int] = {}
    blank_critical = 0
    unresolved_critical = 0
    formula_in_values = 0

    for row in rows:
        rid = row.get("review_row_id", "")
        decision = (row.get("reviewer_decision") or "").strip()
        fact_type = (row.get("fact_type") or "").strip()
        criticality = (row.get("criticality") or "").strip().lower()
        is_critical = criticality == "critical" or fact_type in critical_types
        row_kind = (row.get("row_kind") or "").strip()

        for field in (
            "raw_value",
            "normalized_value",
            "reviewer_approved_value",
            "reviewer_approved_normalized",
        ):
            val = row.get(field) or ""
            if val.startswith("=FORMULA:") or (val.startswith("=") and field.startswith("reviewer")):
                formula_in_values += 1
                report.fail(f"formula cell rejected in {field} for {rid}")

        if decision and decision not in allowed:
            report.fail(f"unknown decision {decision!r} on {rid}")

        if decision == "CORRECT" and not (row.get("reviewer_approved_value") or "").strip():
            report.fail(f"CORRECT without corrected value on {rid}")

        if not decision:
            decision_counts["UNREVIEWED"] = decision_counts.get("UNREVIEWED", 0) + 1
            if is_critical or row_kind == "missing_critical":
                blank_critical += 1
                unresolved_critical += 1
        else:
            decision_counts[decision] = decision_counts.get(decision, 0) + 1
            if is_critical or row_kind == "missing_critical":
                if decision in {
                    "REQUIRES_LEGAL_JUDGMENT",
                    "UNREADABLE",
                }:
                    unresolved_critical += 1

    approval = (signoff.get("Approval status") or signoff.get("approval_status") or "").strip()
    reviewer_name = (signoff.get("Reviewer name") or signoff.get("reviewer_name") or "").strip()
    primary_checked = (
        signoff.get("Primary evidence checked")
        or signoff.get("primary_evidence_checked")
        or ""
    ).strip().lower()
    demand_not_sot = (
        signoff.get("Demand not used as factual SoT")
        or signoff.get("demand_not_used_as_sot")
        or ""
    ).strip().lower()

    signed = bool(reviewer_name) and bool(approval)
    if require_signoff_for_ok and not signed:
        report.fail("pack is unsigned/unapproved (missing reviewer name or approval status)")

    if approval in {"Approved", "Approved with listed unresolved items"}:
        if unresolved_critical > 0 and approval == "Approved":
            report.fail(
                f"approval 'Approved' with {unresolved_critical} unresolved critical rows"
            )
        if not primary_checked or primary_checked not in {"yes", "true", "y", "1"}:
            report.fail("Approved pack requires confirmation that primary evidence was checked")
        if not demand_not_sot or demand_not_sot not in {"yes", "true", "y", "1"}:
            report.fail(
                "Approved pack requires confirmation that existing demand was not factual SoT"
            )

    if approval and approval not in set(schema.get("allowed_approval_status") or []):
        report.fail(f"unknown approval status {approval!r}")

    report.aggregates = {
        "row_count": len(rows),
        "decision_counts": decision_counts,
        "blank_critical_rows": blank_critical,
        "unresolved_critical_rows": unresolved_critical,
        "formula_value_cells": formula_in_values,
        "approval_status": approval or None,
        "signed": signed,
        "schema_version": schema["schema_version"],
    }
    return report


def validate_paths(
    *,
    csv_path: Path | None,
    xlsx_path: Path | None,
    manifest_path: Path,
    schema_path: Path | None = None,
    expected_row_ids_path: Path | None = None,
    source_root: Path | None = None,
    require_signoff_for_ok: bool = True,
) -> ValidationReport:
    schema = load_schema(schema_path)
    manifest = load_manifest(manifest_path)
    signoff: dict[str, str] = {}
    rows: list[dict[str, str]] = []

    if xlsx_path and xlsx_path.is_file():
        rows, signoff = load_xlsx_rows(xlsx_path)
    elif csv_path and csv_path.is_file():
        rows = load_csv_rows(csv_path)
        # CSV packs may include a companion signoff JSON
        side = csv_path.with_name("phase05_firm_gold_signoff.json")
        if side.is_file():
            signoff = json.loads(side.read_text(encoding="utf-8"))
    else:
        report = ValidationReport()
        report.fail("no workbook or CSV provided")
        return report

    expected_ids = None
    if expected_row_ids_path and expected_row_ids_path.is_file():
        expected_ids = json.loads(expected_row_ids_path.read_text(encoding="utf-8"))
    elif xlsx_path and xlsx_path.is_file() and manifest.get("xlsx_review_row_ids"):
        expected_ids = list(manifest["xlsx_review_row_ids"])
    elif manifest.get("review_row_ids"):
        expected_ids = list(manifest["review_row_ids"])

    disk_hashes = None
    if source_root is not None and manifest.get("source_paths_by_alias"):
        # optional: recompute from private path map in manifest (gitignored only)
        import hashlib

        disk_hashes = {}
        for alias, rel in (manifest.get("source_paths_by_alias") or {}).items():
            p = Path(rel)
            if not p.is_file():
                p = source_root / rel
            if p.is_file():
                disk_hashes[alias] = hashlib.sha256(p.read_bytes()).hexdigest()

    return validate_pack(
        rows=rows,
        manifest=manifest,
        schema=schema,
        signoff=signoff,
        source_hashes_on_disk=disk_hashes,
        expected_row_ids=expected_ids,
        require_signoff_for_ok=require_signoff_for_ok,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=None)
    parser.add_argument("--xlsx", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--expected-ids", type=Path, default=None)
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--allow-unsigned", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    report = validate_paths(
        csv_path=args.csv,
        xlsx_path=args.xlsx,
        manifest_path=args.manifest,
        schema_path=args.schema,
        expected_row_ids_path=args.expected_ids,
        source_root=args.source_root,
        require_signoff_for_ok=not args.allow_unsigned,
    )
    payload = report.to_dict()
    text = json.dumps(payload, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())

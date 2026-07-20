"""Generate Phase 5 firm-gold lawyer review pack (private outputs under tmp/).

Does not modify production FactService behavior beyond running normal extract APIs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.server_settings import ServerSettings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.app_settings import AppSettings  # noqa: E402
from app.models.case_session import CaseSession  # noqa: E402
from app.services.classification.authority import is_primary_authoritative  # noqa: E402
from app.services.facts.types import CRITICAL_FACT_TYPES  # noqa: E402

SCHEMA_PATH = ROOT / "scripts" / "phase05_gold_review_schema.json"
OUT_DIR = ROOT / "tmp" / "phase05" / "firm-gold-review"
EXAMPLE = ROOT / "docs" / "example"
IMPL_COMMIT = "cab86da303ae4340729d56a68194b92c90c4dab1"
SCHEMA_VERSION = "phase05-firm-gold-review.v1"
CATALOG_VERSION = "0.1-provisional"
CONTRACTS_VERSION = "0.1"

KNOWN_SHA16 = {
    "167b9052da1b662e": "ecw_billing",
    "9fc3d498462cb55a": "ecw_medical",
    "797da053c3a988c5": "police",
    "8212e9d305a0bae1": "insurer",
}

ROW_FIELDS = [
    "review_row_id",
    "fact_or_issue_id",
    "conflict_group_id",
    "fact_type",
    "criticality",
    "document_alias",
    "document_category",
    "authority_state",
    "page_number",
    "source_span_ids",
    "raw_value",
    "normalized_value",
    "display_value",
    "system_status",
    "classification_ambiguous",
    "source_method",
    "parser_id",
    "calculation_input_ids",
    "system_warning",
    "row_kind",
    "sheet_hint",
    "context_snippet",
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
]

DECISIONS = [
    "APPROVE",
    "CORRECT",
    "REJECT_FALSE_POSITIVE",
    "NOT_PRESENT",
    "UNREADABLE",
    "REQUIRES_LEGAL_JUDGMENT",
    "DUPLICATE",
    "WRONG_FACT_TYPE",
    "WRONG_SOURCE",
    "MISSING_EXPECTED_FACT",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha16(path: Path) -> str:
    return sha256_file(path)[:16]


def git_rev(rev: str = "HEAD") -> str:
    return (
        subprocess.check_output(["git", "rev-parse", rev], cwd=ROOT, text=True).strip()
    )


def resolve_package() -> dict[str, Path]:
    found: dict[str, Path] = {}
    known = set(KNOWN_SHA16)
    docx: list[Path] = []
    if not EXAMPLE.is_dir():
        return found
    for p in EXAMPLE.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in {".pdf", ".docx"}:
            continue
        h = sha16(p)
        if h in KNOWN_SHA16:
            found[KNOWN_SHA16[h]] = p
        elif p.suffix.lower() == ".docx":
            docx.append(p)
        elif p.suffix.lower() == ".pdf" and p.stat().st_size > 4_000_000 and h not in known:
            if "long_medical" not in found:
                found["long_medical"] = p
    docx.sort(key=lambda x: x.stat().st_size)
    if docx:
        found["existing_demand"] = docx[0]
        for i, p in enumerate(docx[1:], start=1):
            found[f"jackman_demand_{i}"] = p
    spike = ROOT / "spikes" / "docx-template" / "out" / "jackman_like_demand_template.docx"
    if spike.is_file():
        found["template"] = spike
    return found


def _blank_reviewer() -> dict[str, str]:
    return {
        "reviewer_decision": "",
        "reviewer_approved_value": "",
        "reviewer_approved_normalized": "",
        "reviewer_approved_fact_type": "",
        "correct_source_alias": "",
        "correct_source_page": "",
        "reviewer_confidence": "",
        "reviewer_comments": "",
        "review_date": "",
        "reviewer_initials": "",
    }


def _parse_desc(desc: str | None) -> tuple[str, bool, bool, str]:
    text = desc or ""
    parser_id = ""
    for part in text.split(";"):
        if part.startswith("parser:"):
            parser_id = part[len("parser:") :]
    ambiguous = "classification:ambiguous" in text
    secondary = "authority:secondary" in text
    warnings = ""
    if "warnings:" in text:
        warnings = text.split("warnings:", 1)[1]
    return parser_id, ambiguous, secondary, warnings


def _calc_inputs(desc: str | None) -> str:
    text = desc or ""
    if "inputs:" in text:
        return text.split("inputs:", 1)[1].split("|")[0]
    return ""


def _source_method(fact: dict[str, Any], span_methods: dict[str, str]) -> str:
    if fact.get("provenance") == "calculated":
        return "calculated"
    methods = fact.get("extraction_methods") or []
    if methods:
        joined = ",".join(str(m) for m in methods)
        if "ocr" in joined.lower():
            return "ocr"
        if "native" in joined.lower():
            return "native"
        if "calculation" in joined.lower():
            return "calculated"
    for sid in fact.get("source_span_ids") or []:
        m = span_methods.get(sid)
        if m:
            return m
    return "unknown"


def extract_snapshot(paths: dict[str, Path]) -> dict[str, Any]:
    order = [
        "police",
        "insurer",
        "ecw_medical",
        "ecw_billing",
        "long_medical",
        "existing_demand",
        "template",
    ] + sorted(k for k in paths if k.startswith("jackman_demand_"))

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        app = create_app(
            app_settings=AppSettings(),
            server_settings=ServerSettings(
                cors_origins=["http://localhost:5173"],
                log_level="WARNING",
                app_version="0.0.0-phase05-gold",
                temp_root=tmp / "sessions",
                max_active_sessions=32,
                session_cleanup_interval_seconds=3600,
            ),
        )
        upload = []
        alias_by_name: dict[str, str] = {}
        for alias in order:
            if alias not in paths:
                continue
            p = paths[alias]
            safe = f"{alias}{p.suffix.lower()}"
            mime = (
                "application/pdf"
                if p.suffix.lower() == ".pdf"
                else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            upload.append((safe, p.read_bytes(), mime))
            alias_by_name[safe] = alias

        t0 = time.perf_counter()
        with TestClient(app) as client:
            session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
            sid = session.id
            up = client.post(
                f"/api/v1/sessions/{sid}/documents",
                files=[("files", f) for f in upload],
            )
            if up.status_code != 200:
                raise RuntimeError(f"upload failed: {up.text[:500]}")
            assert client.post(f"/api/v1/sessions/{sid}/process").status_code == 200
            client.app.state.process_service.wait_until_idle(sid, timeout=900)
            process_ms = (time.perf_counter() - t0) * 1000

            docs = client.get(f"/api/v1/sessions/{sid}/documents").json()
            facts = client.get(f"/api/v1/sessions/{sid}/facts").json().get("facts", [])
            issues_raw = client.get(f"/api/v1/sessions/{sid}/issues")
            issues = issues_raw.json() if issues_raw.status_code == 200 else []
            if isinstance(issues, dict):
                issues = issues.get("issues", [])

            record = client.app.state.session_service.get_record(sid)
            span_index: dict[str, dict[str, Any]] = {}
            span_methods: dict[str, str] = {}
            for doc_id, by_page in record.spans_by_page.items():
                for page_num, spans in by_page.items():
                    for sp in spans:
                        text = getattr(sp, "text", None) or getattr(sp, "raw_text", None) or ""
                        method = "ocr"
                        em = getattr(sp, "extraction_method", None)
                        if em is not None:
                            method = str(em.value if hasattr(em, "value") else em)
                        elif "native" in str(getattr(sp, "provenance", "")).lower():
                            method = "native"
                        span_index[sp.id] = {
                            "document_id": doc_id,
                            "page_number": page_num,
                            "text": str(text)[:120],
                            "method": method,
                        }
                        span_methods[sp.id] = method

            doc_by_id: dict[str, dict[str, Any]] = {}
            alias_by_doc: dict[str, str] = {}
            for d in docs:
                name = d.get("display_name") or ""
                alias = alias_by_name.get(name, name.split(".")[0])
                alias_by_doc[d["id"]] = alias
                live = record.documents[d["id"]]
                doc_by_id[d["id"]] = {
                    "alias": alias,
                    "classification": d.get("classification"),
                    "classification_status": d.get("classification_status"),
                    "safety_archetype": d.get("safety_archetype"),
                    "exclude_from_drafting": d.get("exclude_from_drafting"),
                    "treat_as_secondary_evidence": d.get("treat_as_secondary_evidence"),
                    "page_count": d.get("page_count") or len(record.pages.get(d["id"], [])),
                    "is_primary_authoritative": is_primary_authoritative(live),
                }

            return {
                "session_id": sid,
                "process_ms": round(process_ms, 1),
                "fact_generation": getattr(record, "fact_generation", None),
                "documents": doc_by_id,
                "alias_by_doc": alias_by_doc,
                "facts": facts,
                "issues": issues,
                "spans": span_index,
                "span_methods": span_methods,
            }


def build_rows(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    facts = snapshot["facts"]
    issues = snapshot["issues"]
    alias_by_doc = snapshot["alias_by_doc"]
    documents = snapshot["documents"]
    spans = snapshot["spans"]
    span_methods = snapshot["span_methods"]

    # Conflict groups by fact_type among CONFLICTING facts
    conflicting = [f for f in facts if f.get("status") == "conflicting"]
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in conflicting:
        by_type[f.get("fact_type") or "unknown"].append(f)
    conflict_group: dict[str, str] = {}
    for ft, members in by_type.items():
        if len({str(m.get("normalized_value")) for m in members}) <= 1:
            continue
        gid = f"cg_{ft.replace('.', '_')}"
        for m in members:
            conflict_group[m["id"]] = gid

    rows: list[dict[str, str]] = []
    seq = 0

    def next_id(prefix: str) -> str:
        nonlocal seq
        seq += 1
        return f"{prefix}_{seq:05d}"

    for fact in facts:
        if fact.get("status") == "rejected":
            continue
        doc_ids = fact.get("document_ids") or []
        doc_id = doc_ids[0] if doc_ids else None
        alias = alias_by_doc.get(doc_id, "") if doc_id else ""
        doc_meta = documents.get(doc_id or "", {})
        parser_id, ambiguous, secondary, warnings = _parse_desc(fact.get("description"))
        span_ids = fact.get("source_span_ids") or []
        page = ""
        snippet = ""
        if span_ids:
            first = spans.get(span_ids[0])
            if first:
                page = str(first.get("page_number") or "")
                snippet = str(first.get("text") or "")[:80]
        fact_type = fact.get("fact_type") or ""
        critical = "critical" if fact_type in CRITICAL_FACT_TYPES else "normal"
        authority = "secondary" if secondary else (
            "primary" if doc_meta.get("is_primary_authoritative") else "non_primary"
        )
        if doc_meta.get("safety_archetype") in {"existing_demand", "template"}:
            authority = f"non_primary:{doc_meta.get('safety_archetype')}"

        row_kind = "fact"
        sheet_hint = "Parser Sample"
        if fact_type in CRITICAL_FACT_TYPES:
            sheet_hint = "Critical Facts"
            row_kind = "critical_fact"
        if fact["id"] in conflict_group:
            sheet_hint = "Conflicts"
            row_kind = "conflict"

        row = {
            "review_row_id": next_id("rr"),
            "fact_or_issue_id": fact["id"],
            "conflict_group_id": conflict_group.get(fact["id"], ""),
            "fact_type": fact_type,
            "criticality": critical,
            "document_alias": alias,
            "document_category": str(doc_meta.get("classification") or ""),
            "authority_state": authority,
            "page_number": page,
            "source_span_ids": "|".join(span_ids),
            "raw_value": str(fact.get("raw_value") or ""),
            "normalized_value": ""
            if fact.get("normalized_value") is None
            else str(fact.get("normalized_value")),
            "display_value": str(fact.get("display_value") or ""),
            "system_status": str(fact.get("status") or ""),
            "classification_ambiguous": "yes" if ambiguous else "no",
            "source_method": _source_method(fact, span_methods),
            "parser_id": parser_id,
            "calculation_input_ids": _calc_inputs(fact.get("description")),
            "system_warning": warnings,
            "row_kind": row_kind,
            "sheet_hint": sheet_hint,
            "context_snippet": snippet,
            **_blank_reviewer(),
        }
        # Dual-list critical conflicts also appear conceptually on Critical — keep single row with Conflicts hint
        if fact_type in CRITICAL_FACT_TYPES and fact["id"] in conflict_group:
            row["sheet_hint"] = "Conflicts"
            row["row_kind"] = "critical_conflict"
        rows.append(row)

    for issue in issues:
        if not isinstance(issue, dict):
            continue
        title = str(issue.get("title") or "")
        # Conflict detector may reuse extraction.missing_critical_fact as a fallback
        # issue_type for types without a dedicated conflict code — only true gaps here.
        if not title.startswith("Missing critical fact:"):
            continue
        if issue.get("issue_type") != "extraction.missing_critical_fact":
            continue
        fact_type = title.replace("Missing critical fact:", "").strip() or "unknown"
        rows.append(
            {
                "review_row_id": next_id("rr"),
                "fact_or_issue_id": issue.get("id") or "",
                "conflict_group_id": "",
                "fact_type": fact_type,
                "criticality": "critical",
                "document_alias": "",
                "document_category": "",
                "authority_state": "",
                "page_number": "",
                "source_span_ids": "",
                "raw_value": "",
                "normalized_value": "",
                "display_value": "",
                "system_status": "missing",
                "classification_ambiguous": "no",
                "source_method": "",
                "parser_id": "",
                "calculation_input_ids": "",
                "system_warning": str(issue.get("explanation") or "")[:200],
                "row_kind": "missing_critical",
                "sheet_hint": "Critical Facts",
                "context_snippet": "",
                **_blank_reviewer(),
            }
        )

    return rows


def select_parser_sample(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Noncritical rows: all if ≤5 per fact_type else 5 diverse."""
    noncrit = [
        r
        for r in rows
        if r["sheet_hint"] == "Parser Sample" or (
            r["row_kind"] == "fact" and r["criticality"] != "critical" and not r["conflict_group_id"]
        )
    ]
    # Prefer rows already tagged Parser Sample; also include noncritical non-conflict
    candidates = [
        r
        for r in rows
        if r["criticality"] != "critical"
        and r["row_kind"] not in {"missing_critical", "critical_conflict", "conflict"}
        and not r.get("conflict_group_id")
    ]
    by_type: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in candidates:
        by_type[r["fact_type"]].append(r)

    selected: list[dict[str, str]] = []
    for _ft, members in sorted(by_type.items()):
        if len(members) <= 5:
            chosen = members
        else:
            # diversify by alias / method / ambiguous
            scored = []
            seen: set[tuple[str, str, str]] = set()
            for m in members:
                key = (m["document_alias"], m["source_method"], m["classification_ambiguous"])
                scored.append((0 if key in seen else 1, m))
                seen.add(key)
            scored.sort(key=lambda x: -x[0])
            chosen = [m for _, m in scored[:5]]
        for m in chosen:
            copy = dict(m)
            copy["sheet_hint"] = "Parser Sample"
            selected.append(copy)
    return selected


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=ROW_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in ROW_FIELDS})


def write_xlsx(
    path: Path,
    *,
    all_rows: list[dict[str, str]],
    parser_sample: list[dict[str, str]],
    documents: dict[str, Any],
    aggregates: dict[str, Any],
) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()

    # Instructions
    ws = wb.active
    ws.title = "Instructions"
    instructions = [
        "Phase 5 firm gold validation — lawyer / paralegal review",
        "",
        "Purpose: validate deterministic fact extraction against PRIMARY evidence.",
        "This is validation, not demand drafting.",
        "System values are PROPOSALS only. Blank reviewer fields are NOT approval.",
        "Do NOT use the existing demand letter as the factual answer key (FR-CLS-06).",
        "Verify each fact against police / insurer / medical / billing evidence pages.",
        "",
        "How to locate evidence: use document_alias + page_number + source_span_ids.",
        "Optional private context_snippet is Git-ignored and may be truncated.",
        "",
        "Allowed reviewer_decision values:",
        ", ".join(DECISIONS),
        "",
        "CORRECT requires reviewer_approved_value.",
        "Add false-negative expected facts only on the Missing Facts sheet.",
        "Do not delete rows. Do not rename sheets or this file.",
        "Complete Sign-off only after reviewing critical rows.",
        "Do not upload case files to public AI services.",
    ]
    for i, line in enumerate(instructions, start=1):
        ws.cell(i, 1, line)

    header_fill = PatternFill("solid", fgColor="D9E2F3")
    editable_fill = PatternFill("solid", fgColor="FFF2CC")
    locked_font = Font(color="000000")

    def write_sheet(name: str, rows: list[dict[str, str]], include_snippet: bool) -> None:
        w = wb.create_sheet(name)
        fields = [f for f in ROW_FIELDS if include_snippet or f != "context_snippet"]
        for col, field in enumerate(fields, start=1):
            cell = w.cell(1, col, field)
            cell.fill = header_fill
            cell.font = Font(bold=True)
        dv = DataValidation(
            type="list",
            formula1='"' + ",".join(DECISIONS) + '"',
            allow_blank=True,
        )
        conf_dv = DataValidation(
            type="list",
            formula1='"Clear,Unclear,Unreadable"',
            allow_blank=True,
        )
        w.add_data_validation(dv)
        w.add_data_validation(conf_dv)
        decision_col = fields.index("reviewer_decision") + 1
        conf_col = fields.index("reviewer_confidence") + 1
        for r_idx, row in enumerate(rows, start=2):
            for c_idx, field in enumerate(fields, start=1):
                val = row.get(field, "")
                cell = w.cell(r_idx, c_idx, val)
                if field.startswith("reviewer_") or field in {
                    "correct_source_alias",
                    "correct_source_page",
                    "review_date",
                    "reviewer_initials",
                }:
                    cell.fill = editable_fill
                else:
                    cell.font = locked_font
            dv.add(w.cell(r_idx, decision_col))
            conf_dv.add(w.cell(r_idx, conf_col))
        for col in range(1, len(fields) + 1):
            w.column_dimensions[get_column_letter(col)].width = 18

    critical_rows = [
        r
        for r in all_rows
        if r["sheet_hint"] == "Critical Facts"
        or r["row_kind"] in {"critical_fact", "missing_critical"}
    ]
    # Critical conflicts also belong on Critical for review completeness (copy)
    critical_extra = [
        dict(r, sheet_hint="Critical Facts")
        for r in all_rows
        if r["row_kind"] == "critical_conflict"
    ]
    # Avoid duplicate review_row_id on Critical: include conflict rows only on Conflicts;
    # critical_conflict already has unique id on Conflicts sheet. Add note rows? Plan says
    # Critical Facts include conflicting critical — include those rows on Critical as well
    # would duplicate IDs. Keep single row on Conflicts with critical_conflict kind;
    # also add them to Critical Facts list as the same row object reference once.
    critical_ids = {r["review_row_id"] for r in critical_rows}
    for r in all_rows:
        if r["row_kind"] == "critical_conflict" and r["review_row_id"] not in critical_ids:
            critical_rows.append(r)

    conflict_rows = [
        r for r in all_rows if r["conflict_group_id"] or r["row_kind"] in {"conflict", "critical_conflict"}
    ]

    write_sheet("Critical Facts", critical_rows, include_snippet=True)
    write_sheet("Conflicts", conflict_rows, include_snippet=True)
    write_sheet("Parser Sample", parser_sample, include_snippet=True)

    # Missing Facts — template rows for reviewer FN entry
    miss = wb.create_sheet("Missing Facts")
    fn_fields = [
        "review_row_id",
        "fact_type",
        "reviewer_approved_value",
        "reviewer_approved_normalized",
        "correct_source_alias",
        "correct_source_page",
        "reviewer_confidence",
        "reviewer_comments",
        "reviewer_decision",
        "review_date",
        "reviewer_initials",
        "row_kind",
    ]
    for col, field in enumerate(fn_fields, start=1):
        cell = miss.cell(1, col, field)
        cell.fill = header_fill
        cell.font = Font(bold=True)
    for i in range(2, 52):
        miss.cell(i, 1, f"fn_{i - 1:04d}")
        miss.cell(i, 12, "false_negative_template")
        for col in range(2, 12):
            miss.cell(i, col, "").fill = editable_fill
    dv = DataValidation(type="list", formula1='"' + ",".join(DECISIONS) + '"', allow_blank=True)
    miss.add_data_validation(dv)
    decision_col = fn_fields.index("reviewer_decision") + 1
    for i in range(2, 52):
        dv.add(miss.cell(i, decision_col))

    # Document Inventory
    inv = wb.create_sheet("Document Inventory")
    inv_headers = [
        "alias",
        "classification",
        "classification_status",
        "safety_archetype",
        "authority",
        "page_count",
        "exclude_from_drafting",
        "review_status",
    ]
    for col, h in enumerate(inv_headers, start=1):
        cell = inv.cell(1, col, h)
        cell.fill = header_fill
        cell.font = Font(bold=True)
    for r_idx, (_did, meta) in enumerate(sorted(documents.items(), key=lambda x: x[1]["alias"]), start=2):
        inv.cell(r_idx, 1, meta["alias"])
        inv.cell(r_idx, 2, meta.get("classification"))
        inv.cell(r_idx, 3, meta.get("classification_status"))
        inv.cell(r_idx, 4, meta.get("safety_archetype"))
        inv.cell(
            r_idx,
            5,
            "primary" if meta.get("is_primary_authoritative") else "non_primary",
        )
        inv.cell(r_idx, 6, meta.get("page_count"))
        inv.cell(r_idx, 7, meta.get("exclude_from_drafting"))
        inv.cell(r_idx, 8, "").fill = editable_fill

    # Summary
    summary = wb.create_sheet("Summary")
    summary["A1"] = "Metric"
    summary["B1"] = "Count"
    summary["A1"].fill = header_fill
    summary["B1"].fill = header_fill
    metrics = [
        ("total_review_rows_csv", aggregates.get("total_rows")),
        ("critical_rows", aggregates.get("critical_rows")),
        ("conflict_rows", aggregates.get("conflict_rows")),
        ("missing_critical_rows", aggregates.get("missing_critical_rows")),
        ("parser_sample_rows", aggregates.get("parser_sample_rows")),
        ("document_alias_count", aggregates.get("document_alias_count")),
        ("fact_type_coverage", aggregates.get("fact_type_count")),
        ("Note", "Fill decision counts after review; do not treat blanks as approved"),
    ]
    for i, (k, v) in enumerate(metrics, start=2):
        summary.cell(i, 1, k)
        summary.cell(i, 2, v if not isinstance(v, list) else len(v))

    # Sign-off
    so = wb.create_sheet("Sign-off")
    fields = [
        ("Reviewer name", ""),
        ("Reviewer role", ""),
        ("Firm/organisation", ""),
        ("Review completion date", ""),
        ("Primary evidence checked", ""),
        ("Demand not used as factual SoT", ""),
        ("Approval status", ""),
        ("Reviewer comments", ""),
        ("Signature/initials", ""),
    ]
    so["A1"] = "Field"
    so["B1"] = "Value"
    so["A1"].fill = header_fill
    so["B1"].fill = header_fill
    for i, (label, val) in enumerate(fields, start=2):
        so.cell(i, 1, label)
        cell = so.cell(i, 2, val)
        cell.fill = editable_fill
    so["A12"] = "Allowed Approval status values:"
    so["A13"] = "Approved | Approved with listed unresolved items | Not approved"
    so["A14"] = "Primary evidence checked / Demand not used: Yes or No"
    adv = DataValidation(
        type="list",
        formula1='"Approved,Approved with listed unresolved items,Not approved"',
        allow_blank=True,
    )
    so.add_data_validation(adv)
    adv.add(so["B8"])

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def self_validate(
    *,
    rows: list[dict[str, str]],
    snapshot: dict[str, Any],
    parser_sample: list[dict[str, str]],
) -> dict[str, Any]:
    errors: list[str] = []
    span_index = snapshot["spans"]
    for r in rows:
        if r["row_kind"] == "missing_critical":
            continue
        for sid in (r["source_span_ids"] or "").split("|"):
            if not sid:
                continue
            if sid not in span_index:
                errors.append(f"missing span {sid}")
            elif not sid.startswith("span_"):
                errors.append(f"bad span prefix {sid}")

    critical_types_present = {
        r["fact_type"] for r in rows if r["criticality"] == "critical" or r["row_kind"] == "missing_critical"
    }
    conflict_rows = [r for r in rows if r["conflict_group_id"]]
    missing_rows = [r for r in rows if r["row_kind"] == "missing_critical"]

    # Parser family coverage from registry ids in sample+all
    parser_ids = {r["parser_id"] for r in rows if r["parser_id"]}
    parser_ids |= {r["parser_id"] for r in parser_sample if r["parser_id"]}

    demand_primary_verified = [
        r
        for r in rows
        if "existing_demand" in (r["authority_state"] or "")
        and r["system_status"] == "verified"
        and "non_primary" not in r["authority_state"]
    ]
    # Our authority_state uses non_primary:existing_demand — verified primary should be empty
    bad_demand = [
        r
        for r in rows
        if r["document_category"] in {"existing_demand", "template"}
        and r["system_status"] == "verified"
        and not r["authority_state"].startswith("non_primary")
    ]

    blank_decisions = all(not r["reviewer_decision"] for r in rows)
    calc_ok = all(
        r["calculation_input_ids"] or r["source_method"] != "calculated"
        for r in rows
        if r["source_method"] == "calculated"
    )

    return {
        "ok": len(errors) == 0 and blank_decisions and not bad_demand and calc_ok,
        "span_errors": len(errors),
        "span_error_sample": errors[:10],
        "critical_type_count": len(critical_types_present),
        "conflict_row_count": len(conflict_rows),
        "missing_critical_row_count": len(missing_rows),
        "parser_id_count": len(parser_ids),
        "blank_reviewer_decisions": blank_decisions,
        "demand_template_not_primary_verified": len(bad_demand) == 0,
        "calc_inputs_present": calc_ok,
        "parser_sample_count": len(parser_sample),
        "total_rows": len(rows),
    }


def maybe_backup(path: Path, force: bool) -> None:
    if not path.exists():
        return
    # Detect completed review: any non-blank decision in CSV sibling or xlsx signoff
    if not force:
        raise SystemExit(
            f"Refusing to overwrite existing {path.name}. Use --force to backup and regenerate."
        )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.stem}.backup-{stamp}{path.suffix}")
    shutil.copy2(path, backup)
    print(f"Backed up to {backup}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-extract", action="store_true", help="Reuse existing snapshot")
    args = parser.parse_args(argv)

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = out_dir / "phase05_firm_gold_review.xlsx"
    csv_path = out_dir / "phase05_firm_gold_review.csv"
    snap_path = out_dir / "phase05_extraction_snapshot.json"
    manifest_path = out_dir / "phase05_firm_gold_manifest.json"

    for p in (xlsx_path, csv_path):
        if p.exists():
            maybe_backup(p, args.force)

    paths = resolve_package()
    required = ["police", "insurer", "ecw_medical", "ecw_billing", "long_medical", "existing_demand"]
    missing = [a for a in required if a not in paths]
    if missing:
        raise SystemExit(f"reference package incomplete, missing aliases: {missing}")

    if args.skip_extract and snap_path.is_file():
        snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
    else:
        print("Extracting reference package (real OCR)…")
        snapshot = extract_snapshot(paths)
        # Persist private snapshot (may contain values)
        snap_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    rows = build_rows(snapshot)
    parser_sample = select_parser_sample(rows)

    # Ensure every fact_type from rows appears in CSV; sample is subset
    write_csv(csv_path, rows)

    type_counts = Counter(r["fact_type"] for r in rows)
    aggregates = {
        "total_rows": len(rows),
        "critical_rows": sum(
            1
            for r in rows
            if r["row_kind"] in {"critical_fact", "missing_critical", "critical_conflict"}
            or (r["criticality"] == "critical" and r["sheet_hint"] == "Critical Facts")
        ),
        "conflict_rows": sum(1 for r in rows if r["conflict_group_id"]),
        "missing_critical_rows": sum(1 for r in rows if r["row_kind"] == "missing_critical"),
        "parser_sample_rows": len(parser_sample),
        "document_alias_count": len(paths),
        "fact_type_count": len(type_counts),
        "fact_types": sorted(type_counts),
    }
    # Refine critical count
    aggregates["critical_rows"] = sum(
        1
        for r in rows
        if r["criticality"] == "critical" or r["row_kind"] == "missing_critical"
    )

    write_xlsx(
        xlsx_path,
        all_rows=rows,
        parser_sample=parser_sample,
        documents=snapshot["documents"],
        aggregates=aggregates,
    )

    tip = git_rev("HEAD")
    source_hashes = {alias: sha256_file(p) for alias, p in paths.items()}
    # Store only relative paths under docs/example for private rematch — not absolute
    source_rel = {}
    for alias, p in paths.items():
        try:
            source_rel[alias] = str(p.relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            source_rel[alias] = p.name

    self_check = self_validate(rows=rows, snapshot=snapshot, parser_sample=parser_sample)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "implementation_commit": IMPL_COMMIT,
        "branch_tip_commit": tip,
        "parser_catalog_version": CATALOG_VERSION,
        "contracts_version": CONTRACTS_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "document_aliases": sorted(paths),
        "document_alias_count": len(paths),
        "page_counts_by_alias": {
            meta["alias"]: meta.get("page_count")
            for meta in snapshot["documents"].values()
        },
        "classification_by_alias": {
            meta["alias"]: {
                "classification": meta.get("classification"),
                "classification_status": meta.get("classification_status"),
                "safety_archetype": meta.get("safety_archetype"),
                "is_primary_authoritative": meta.get("is_primary_authoritative"),
            }
            for meta in snapshot["documents"].values()
        },
        "fact_candidate_count": len(snapshot["facts"]),
        "issue_count": len(snapshot["issues"]),
        "fact_generation": snapshot.get("fact_generation"),
        "process_ms": snapshot.get("process_ms"),
        "review_row_ids": [r["review_row_id"] for r in rows],
        "xlsx_review_row_ids": sorted(
            {
                *(r["review_row_id"] for r in rows if r["criticality"] == "critical" or r["row_kind"] == "missing_critical"),
                *(r["review_row_id"] for r in rows if r["conflict_group_id"]),
                *(r["review_row_id"] for r in parser_sample),
            }
        ),
        "aggregates": aggregates,
        "self_check": self_check,
        "source_sha256_by_alias": source_hashes,
        "source_paths_by_alias": source_rel,
        "llm_calls": 0,
        "note": "Private manifest — do not commit. Hashes and values are local-only.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    shutil.copy2(SCHEMA_PATH, out_dir / "phase05_review_schema.json")

    readme = out_dir / "README.txt"
    readme.write_text(
        "\n".join(
            [
                "Phase 5 firm gold review pack",
                "=============================",
                "",
                "SEND TO REVIEWER:",
                "  phase05_firm_gold_review.xlsx",
                "",
                "RETURN FROM REVIEWER:",
                "  The same file: phase05_firm_gold_review.xlsx (completed decisions + Sign-off)",
                "",
                "Do not rename the workbook or sheet names.",
                "Do not delete rows. Add false-negative facts only on Missing Facts.",
                "Do not upload evidence PDFs/DOCX to public services.",
                "Existing demand letters are not the factual answer key.",
                "",
                f"Schema: {SCHEMA_VERSION}",
                f"Implementation commit: {IMPL_COMMIT}",
                "",
                "After return, run:",
                "  python scripts/validate_phase05_gold_review.py --xlsx <returned.xlsx> "
                "--manifest phase05_firm_gold_manifest.json --allow-unsigned  # while drafting",
                "  (omit --allow-unsigned for final acceptance check)",
            ]
        ),
        encoding="utf-8",
    )

    # Safe aggregate for committed prep report
    safe = {
        "schema_version": SCHEMA_VERSION,
        "implementation_commit": IMPL_COMMIT,
        "branch_tip_commit": tip,
        "aggregates": aggregates,
        "self_check": {
            k: v for k, v in self_check.items() if k != "span_error_sample"
        },
        "status_counts": dict(Counter(f.get("status") for f in snapshot["facts"])),
    }
    (out_dir / "phase05_safe_aggregates.json").write_text(
        json.dumps(safe, indent=2), encoding="utf-8"
    )

    print(json.dumps(safe, indent=2))
    if not self_check["ok"]:
        print("SELF-CHECK FAILED", self_check, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

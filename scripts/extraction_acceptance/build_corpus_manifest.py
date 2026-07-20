"""Build private acceptance corpus manifest (gitignored outputs)."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docs" / "example"
FORENSIC_PAGES = ROOT / "tmp" / "extraction-forensic-investigation" / "pages"
OUT = ROOT / "tmp" / "extraction-remediation" / "acceptance-corpus"
INTAKE = ROOT / "tmp" / "extraction-remediation" / "intake"

# Safe aliases only in committed docs; hashes stay private under tmp/.
DOC_SPECS: list[dict] = [
    {
        "safe_alias": "police",
        "family": "police_report",
        "globs": ["EG90156.pdf"],
        "inclusion_reason": "Primary police report family for native/form challenges",
    },
    {
        "safe_alias": "insurer",
        "family": "insurer_correspondence",
        "globs": ["*Dairyland*.pdf", "*Patriot*.pdf", "*Insurance*.pdf"],
        "inclusion_reason": "Insurer correspondence narrative and identifiers",
    },
    {
        "safe_alias": "ecw_medical",
        "family": "medical_record",
        "globs": ["*eCW*Medical*.pdf"],
        "inclusion_reason": "Digital EMR native text; name anchors",
    },
    {
        "safe_alias": "ecw_billing",
        "family": "bill_ledger",
        "globs": ["*eCW*Billing*.pdf"],
        "inclusion_reason": "Billing ledger / table-like layout",
    },
    {
        "safe_alias": "long_medical",
        "family": "medical_record",
        "globs": ["*MEDICAL RECORDS*.pdf", "*JACKMAN*.pdf"],
        "inclusion_reason": "Long clinical stack; mixed quality pages",
    },
    {
        "safe_alias": "existing_demand",
        "family": "existing_demand",
        "globs": ["Demand Mayel*.docx", "*Amini*Final*.docx"],
        "inclusion_reason": "Existing demand letterhead / firm name",
    },
    {
        "safe_alias": "demand_ahmed",
        "family": "existing_demand",
        "globs": ["*Ahmed*.docx"],
        "inclusion_reason": "Additional demand template-like document",
    },
    {
        "safe_alias": "demand_morris",
        "family": "existing_demand",
        "globs": ["*Morris*.docx"],
        "inclusion_reason": "Additional demand document family coverage",
    },
    {
        "safe_alias": "demand_fuentes",
        "family": "existing_demand",
        "globs": ["*Fuentes*.docx"],
        "inclusion_reason": "Additional demand document family coverage",
    },
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _find(globs: list[str]) -> Path | None:
    if not EXAMPLE.is_dir():
        return None
    for pattern in globs:
        hits = sorted(EXAMPLE.glob(pattern))
        if hits:
            return hits[0]
    return None


def _page_count(path: Path) -> int | None:
    if path.suffix.lower() != ".pdf":
        return None
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            return len(pdf.pages)
    except Exception:  # noqa: BLE001
        return None


def _forensic_selected_pages() -> list[dict]:
    pages: list[dict] = []
    if not FORENSIC_PAGES.is_dir():
        return pages
    for d in sorted(FORENSIC_PAGES.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "page_meta.json"
        meta = {}
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        pages.append(
            {
                "page_id": d.name,
                "safe_alias": meta.get("alias") or d.name.rsplit("_", 1)[0],
                "page_number": meta.get("page_number"),
                "selection_reason": meta.get("reason") or f"forensic seed {d.name}",
                "source": "forensic_investigation",
                "annotation_status": "machine_prefill",
            }
        )
    return pages


def _extra_pages_for_alias(alias: str, page_count: int | None) -> list[dict]:
    """Add a few extra pages beyond forensic seed for coverage."""
    extras: list[dict] = []
    plans = {
        "police": [1, 2, 4],  # p4 low-text / image-like
        "insurer": [1],
        "ecw_medical": [1, 15, 20],
        "ecw_billing": [1],
        "long_medical": [1, 2, 19, 36],
    }
    for pn in plans.get(alias, [1]):
        if page_count is not None and pn > page_count:
            continue
        extras.append(
            {
                "page_id": f"{alias}_p{pn}",
                "safe_alias": alias,
                "page_number": pn,
                "selection_reason": f"representative {alias} page {pn}",
                "source": "corpus_selection",
                "annotation_status": "unreviewed",
            }
        )
    return extras


def build() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    INTAKE.mkdir(parents=True, exist_ok=True)

    inventory_rows: list[dict] = []
    missing: list[str] = []
    for spec in DOC_SPECS:
        path = _find(spec["globs"])
        if path is None:
            missing.append(spec["safe_alias"])
            inventory_rows.append(
                {
                    "safe_alias": spec["safe_alias"],
                    "family": spec["family"],
                    "present": False,
                    "file_type": "",
                    "page_count": "",
                    "file_hash": "",
                    "inclusion_reason": spec["inclusion_reason"],
                }
            )
            continue
        digest = _sha256(path)
        pc = _page_count(path)
        inventory_rows.append(
            {
                "safe_alias": spec["safe_alias"],
                "family": spec["family"],
                "present": True,
                "file_type": path.suffix.lower().lstrip("."),
                "page_count": pc if pc is not None else "",
                "file_hash": digest,
                "inclusion_reason": spec["inclusion_reason"],
                "native_image_mixed": "unknown",
                "hidden_text_layer": "unknown",
                "handwriting": "unknown",
                "table_form": "yes" if spec["family"] == "bill_ledger" else "unknown",
                "rotation_skew": "unknown",
                "known_quality_challenge": (
                    "low_text_page" if spec["safe_alias"] == "police" else ""
                ),
            }
        )

    # Difficult badge police report — not located as 9065/Go6s pair
    missing_badge_doc = True
    intake_readme = INTAKE / "README.txt"
    intake_readme.write_text(
        "PRIVATE INTAKE — Extraction Remediation Part 1\n"
        "==============================================\n\n"
        "Missing file for final Part 1 acceptance:\n"
        "  - Difficult two-page police report whose visible badge/ID reads 9065\n"
        "    and whose corrupt embedded text candidate reads Go6s.\n\n"
        "EG90156.pdf is present as the general police family but does not expose\n"
        "the 9065 / Go6s pair in native pdfplumber text. Do not fabricate\n"
        "annotations for 9065 from machine output alone.\n\n"
        "Place the missing PDF in this intake directory when available, then\n"
        "re-run build_corpus_manifest.py and seed USER_CONFIRMED_ANCHOR for badge.\n",
        encoding="utf-8",
    )

    selected = _forensic_selected_pages()
    seen = {(p["safe_alias"], p["page_number"]) for p in selected}
    for row in inventory_rows:
        if not row.get("present"):
            continue
        alias = row["safe_alias"]
        pc = row["page_count"] if isinstance(row["page_count"], int) else None
        for extra in _extra_pages_for_alias(alias, pc):
            key = (extra["safe_alias"], extra["page_number"])
            if key not in seen:
                selected.append(extra)
                seen.add(key)

    # Cap ~50 pages
    if len(selected) > 50:
        selected = selected[:50]

    # Known anchors (private file; values allowed here under tmp/)
    anchors = [
        {
            "anchor_id": "client_name",
            "status": "USER_CONFIRMED_ANCHOR",
            "field_type": "person_name",
            "expected": "Mayel Amini",
            "pages_available": True,
            "notes": "Seed where client name appears; do not infer surrounding fields",
        },
        {
            "anchor_id": "law_firm",
            "status": "USER_CONFIRMED_ANCHOR",
            "field_type": "law_firm_name",
            "expected": "The Jackman Law Firm, PLLC",
            "pages_available": True,
            "notes": "Seed on demand/letterhead pages when present",
        },
        {
            "anchor_id": "police_badge",
            "status": "USER_CONFIRMED_ANCHOR",
            "field_type": "badge_id",
            "expected": "9065",
            "corrupt_embedded_candidate": "Go6s",
            "pages_available": False,
            "notes": "Deferred until difficult police intake file is provided",
        },
    ]

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "private": True,
        "document_count_present": sum(1 for r in inventory_rows if r.get("present")),
        "document_count_missing_aliases": missing,
        "selected_page_count": len(selected),
        "selected_pages": selected,
        "difficult_badge_police_report_located": not missing_badge_doc,
        "known_anchors": anchors,
        "annotation_status_summary": {
            "unreviewed": sum(1 for p in selected if p.get("annotation_status") == "unreviewed"),
            "machine_prefill": sum(
                1 for p in selected if p.get("annotation_status") == "machine_prefill"
            ),
            "human_approved": 0,
        },
    }

    annotation_schema = {
        "description": "Private page annotation schema for extraction acceptance",
        "required": [
            "page_id",
            "safe_alias",
            "page_number",
            "annotation_status",
            "expected_transcript",
            "reviewer",
            "review_date",
        ],
        "prefill_label": "UNVERIFIED MACHINE PREFILL",
        "statuses": [
            "unreviewed",
            "machine_prefill",
            "human_approved",
            "disputed",
            "unreadable",
            "USER_CONFIRMED_ANCHOR",
        ],
    }

    ground_truth_status = {
        "corpus_gold": False,
        "human_ground_truth_review": "pending",
        "verdict_hint": "CORPUS PREPARED — HUMAN GROUND-TRUTH REVIEW PENDING",
        "approved_page_count": 0,
        "anchor_coverage": {
            "client_name": "seeded_pending_page_link",
            "law_firm": "seeded_pending_page_link",
            "police_badge_9065": "missing_source_file",
        },
    }

    (OUT / "corpus_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (OUT / "annotation_schema.json").write_text(
        json.dumps(annotation_schema, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "ground_truth_status.json").write_text(
        json.dumps(ground_truth_status, indent=2) + "\n", encoding="utf-8"
    )

    with (OUT / "document_inventory.csv").open("w", encoding="utf-8", newline="") as f:
        fields = [
            "safe_alias",
            "family",
            "present",
            "file_type",
            "page_count",
            "file_hash",
            "inclusion_reason",
            "native_image_mixed",
            "hidden_text_layer",
            "handwriting",
            "table_form",
            "rotation_skew",
            "known_quality_challenge",
        ]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in inventory_rows:
            w.writerow(row)

    with (OUT / "corpus_manifest.csv").open("w", encoding="utf-8", newline="") as f:
        fields = [
            "page_id",
            "safe_alias",
            "page_number",
            "selection_reason",
            "source",
            "annotation_status",
        ]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in selected:
            w.writerow(row)

    (OUT / "README.txt").write_text(
        "PRIVATE acceptance corpus — do not commit.\n"
        "Contains hashes and page selection for local extraction remediation.\n"
        "Machine prefills are UNVERIFIED MACHINE PREFILL, never human gold.\n",
        encoding="utf-8",
    )

    # Safe anchors stub without implying badge page exists
    (OUT / "known_anchors.json").write_text(json.dumps(anchors, indent=2) + "\n", encoding="utf-8")

    return manifest


if __name__ == "__main__":
    m = build()
    print(
        "corpus built:",
        m["document_count_present"],
        "docs,",
        m["selected_page_count"],
        "pages,",
        "badge_located=",
        m["difficult_badge_police_report_located"],
    )

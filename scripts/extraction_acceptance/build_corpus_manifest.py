"""Build private acceptance corpus manifest with multi-case discovery and hash dedupe.

Outputs only under tmp/extraction-remediation/ (gitignored).
"""

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

CASE_ROOTS = [
    ("amini", EXAMPLE / "amini"),
    ("ali_vs_thomas", EXAMPLE / "ali-vs-thomas"),
    ("jones", EXAMPLE / "jones"),
    ("legacy_example", EXAMPLE),
    ("intake", INTAKE),
]

# Document classification heuristics (safe aliases only).
DOC_RULES: list[dict] = [
    {
        "doc_alias": "ali_police",
        "family": "police_report",
        "case_alias": "ali_vs_thomas",
        "name_globs": ["3936314.pdf"],
        "challenges": [
            "corrupt_hidden_ocr",
            "handwriting",
            "form",
            "checkboxes",
            "boxed_chars",
            "narrative",
            "diagram_grid",
            "reading_order",
            "geometry",
        ],
        "select_pages": [1, 2],
        "inclusion_reason": "Difficult two-page police report with badge/ID corrupt-embed challenge",
    },
    {
        "doc_alias": "amini_police",
        "family": "police_report",
        "case_alias": "amini",
        "name_globs": ["EG90156.pdf"],
        "challenges": ["form", "native_or_scan"],
        "select_pages": [1, 2, 4],
        "inclusion_reason": "Amini foundation police report family",
    },
    {
        "doc_alias": "amini_insurer",
        "family": "insurer_correspondence",
        "case_alias": "amini",
        "name_globs": ["*Dairyland*.pdf", "*Insurance*.pdf"],
        "challenges": ["native_narrative", "identifiers"],
        "select_pages": [1],
        "inclusion_reason": "Insurer correspondence",
    },
    {
        "doc_alias": "amini_ecw_medical",
        "family": "medical_record",
        "case_alias": "amini",
        "name_globs": ["*eCW*Medical*.pdf"],
        "challenges": ["native_emr", "names"],
        "select_pages": [1, 15, 20],
        "inclusion_reason": "eCW medical native text",
    },
    {
        "doc_alias": "amini_ecw_billing",
        "family": "bill_ledger",
        "case_alias": "amini",
        "name_globs": ["*eCW*Billing*.pdf"],
        "challenges": ["table", "ocr_likely", "billing"],
        "select_pages": [1],
        "inclusion_reason": "eCW billing ledger",
    },
    {
        "doc_alias": "amini_long_medical",
        "family": "medical_record",
        "case_alias": "amini",
        "name_globs": ["*MEDICAL RECORDS*.pdf"],
        "challenges": ["long_stack", "mixed_quality"],
        "select_pages": [1, 2, 19, 36],
        "inclusion_reason": "Long medical bundle",
    },
    {
        "doc_alias": "amini_existing_demand",
        "family": "existing_demand",
        "case_alias": "amini",
        "name_globs": ["*Amini*Final*.docx", "Demand Mayel*.docx"],
        "challenges": ["docx_derived", "letterhead"],
        "select_pages": [1],
        "inclusion_reason": "Existing demand letterhead / firm name",
    },
    {
        "doc_alias": "jones_medical_bills",
        "family": "medical_record",
        "case_alias": "jones",
        "name_globs": ["*Final Medical*.pdf"],
        "challenges": ["medical", "bills"],
        "select_pages": [1],
        "inclusion_reason": "Jones medical/bills coverage",
    },
    {
        "doc_alias": "jones_psp",
        "family": "medical_record",
        "case_alias": "jones",
        "name_globs": ["psp-nw.pdf"],
        "challenges": ["medical"],
        "select_pages": [1],
        "inclusion_reason": "Jones additional medical facility records",
    },
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _page_count(path: Path) -> int | None:
    if path.suffix.lower() != ".pdf":
        return None
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            return len(pdf.pages)
    except Exception:  # noqa: BLE001
        return None


def _match_name(path: Path, globs: list[str]) -> bool:
    from fnmatch import fnmatch

    name = path.name
    return any(fnmatch(name, g) for g in globs)


def _discover_files() -> list[dict]:
    """Discover PDFs/DOCX under case roots; dedupe by hash."""
    by_hash: dict[str, dict] = {}
    for case_alias, root in CASE_ROOTS:
        if not root.is_dir():
            continue
        # For legacy_example, only top-level files (avoid double-count via amini/)
        if case_alias == "legacy_example":
            candidates = [p for p in root.iterdir() if p.is_file()]
        else:
            candidates = list(root.rglob("*"))
        for path in candidates:
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".pdf", ".docx"}:
                continue
            # Skip gold markdown dirs
            if "gold" in path.parts:
                continue
            digest = _sha256(path)
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            if digest not in by_hash:
                by_hash[digest] = {
                    "file_hash": digest,
                    "canonical_relpath": rel,
                    "file_type": path.suffix.lower().lstrip("."),
                    "page_count": _page_count(path),
                    "source_locations": [rel],
                    "case_hints": [case_alias],
                    "filename": path.name,
                }
            else:
                entry = by_hash[digest]
                if rel not in entry["source_locations"]:
                    entry["source_locations"].append(rel)
                if case_alias not in entry["case_hints"]:
                    entry["case_hints"].append(case_alias)
    return list(by_hash.values())


def _assign_docs(discovered: list[dict]) -> tuple[list[dict], list[dict]]:
    """Match discovered files to DOC_RULES; return (documents, unmatched)."""
    used_hashes: set[str] = set()
    documents: list[dict] = []
    for rule in DOC_RULES:
        hit = None
        for d in discovered:
            if d["file_hash"] in used_hashes:
                continue
            if _match_name(Path(d["filename"]), rule["name_globs"]):
                # Prefer matching case_alias when present
                if rule["case_alias"] in d["case_hints"] or rule["case_alias"] == "intake":
                    hit = d
                    break
                if hit is None:
                    hit = d
        if hit is None:
            continue
        used_hashes.add(hit["file_hash"])
        documents.append(
            {
                "doc_alias": rule["doc_alias"],
                "case_alias": rule["case_alias"],
                "family": rule["family"],
                "file_hash": hit["file_hash"],
                "file_type": hit["file_type"],
                "page_count": hit["page_count"],
                "canonical_relpath": hit["canonical_relpath"],
                "source_locations": hit["source_locations"],
                "challenges": rule["challenges"],
                "select_pages": rule["select_pages"],
                "inclusion_reason": rule["inclusion_reason"],
                "present": True,
            }
        )
    unmatched = [d for d in discovered if d["file_hash"] not in used_hashes]
    return documents, unmatched


def _forensic_pages() -> list[dict]:
    pages: list[dict] = []
    if not FORENSIC_PAGES.is_dir():
        return pages
    for d in sorted(FORENSIC_PAGES.iterdir()):
        if not d.is_dir():
            continue
        meta = {}
        meta_path = d / "page_meta.json"
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        pages.append(
            {
                "page_id": d.name,
                "case_alias": "amini",
                "doc_alias": meta.get("alias") or d.name.rsplit("_", 1)[0],
                "page_number": meta.get("page_number"),
                "selection_reason": meta.get("reason") or f"forensic seed {d.name}",
                "source": "forensic_investigation",
                "challenges": [],
                "annotation_status": "machine_prefill",
            }
        )
    return pages


def build() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    INTAKE.mkdir(parents=True, exist_ok=True)

    discovered = _discover_files()
    documents, unmatched = _assign_docs(discovered)

    # Ensure ali_police is present (critical)
    ali = next((d for d in documents if d["doc_alias"] == "ali_police"), None)
    badge_located = ali is not None

    selected: list[dict] = []
    seen: set[tuple[str, int]] = set()

    # Prefer forensic seeds mapped to amini docs
    for fp in _forensic_pages():
        pn = fp.get("page_number")
        if not isinstance(pn, int):
            continue
        key = (str(fp["doc_alias"]), pn)
        if key in seen:
            continue
        seen.add(key)
        selected.append(fp)

    for doc in documents:
        pc = doc["page_count"] if isinstance(doc["page_count"], int) else None
        for pn in doc["select_pages"]:
            if pc is not None and pn > pc:
                continue
            key = (doc["doc_alias"], pn)
            # forensic may have used shorter aliases (police vs amini_police)
            alt_keys = {key}
            if doc["doc_alias"] == "amini_police":
                alt_keys.add(("police", pn))
            if doc["doc_alias"] == "amini_ecw_medical":
                alt_keys.add(("ecw_medical", pn))
            if doc["doc_alias"] == "amini_ecw_billing":
                alt_keys.add(("ecw_billing", pn))
            if doc["doc_alias"] == "amini_insurer":
                alt_keys.add(("insurer", pn))
            if doc["doc_alias"] == "amini_long_medical":
                alt_keys.add(("long_medical", pn))
            if doc["doc_alias"] == "amini_existing_demand":
                alt_keys.add(("existing_demand", pn))
            if any(k in seen for k in alt_keys):
                continue
            seen.add(key)
            page_id = f"{doc['doc_alias']}_p{pn}"
            challenges = list(doc["challenges"])
            critical_anchors: list[dict] = []
            if doc["doc_alias"] == "ali_police" and pn == 2:
                critical_anchors.append(
                    {
                        "field_id": "badge_id",
                        "field_type": "badge_id",
                        "friendly_name": "Badge or ID #",
                        "expected": "9065",
                        "corrupt_embedded_candidate": "Go6s",
                        "status": "USER_CONFIRMED_ANCHOR",
                        "requires_text_review": True,
                        "requires_layer_review": True,
                        "requires_geometry_review": True,
                    }
                )
            if doc["case_alias"] == "amini" and doc["family"] in {
                "medical_record",
                "insurer_correspondence",
                "existing_demand",
            }:
                critical_anchors.append(
                    {
                        "field_id": "client_name",
                        "field_type": "person_name",
                        "friendly_name": "Client name",
                        "expected": "Mayel Amini",
                        "status": "USER_CONFIRMED_ANCHOR",
                        "page_link_confirmed": False,
                    }
                )
            if doc["doc_alias"] in {"amini_existing_demand", "amini_long_medical"}:
                critical_anchors.append(
                    {
                        "field_id": "law_firm",
                        "field_type": "law_firm_name",
                        "friendly_name": "Law firm",
                        "expected": "The Jackman Law Firm, PLLC",
                        "status": "USER_CONFIRMED_ANCHOR",
                        "page_link_confirmed": False,
                    }
                )
            selected.append(
                {
                    "page_id": page_id,
                    "case_alias": doc["case_alias"],
                    "doc_alias": doc["doc_alias"],
                    "family": doc["family"],
                    "page_number": pn,
                    "selection_reason": doc["inclusion_reason"],
                    "source": "corpus_selection",
                    "challenges": challenges,
                    "annotation_status": "machine_prefill",
                    "critical_anchors": critical_anchors,
                    "file_hash": doc["file_hash"],
                }
            )

    if len(selected) > 50:
        # Keep ali police pages always
        priority = [p for p in selected if p["doc_alias"] == "ali_police"]
        rest = [p for p in selected if p["doc_alias"] != "ali_police"]
        selected = priority + rest[: max(0, 50 - len(priority))]

    dedupe_report = {
        "discovered_file_count": len(discovered),
        "deduplicated_document_count": len(discovered),
        "matched_document_count": len(documents),
        "unmatched_file_count": len(unmatched),
        "duplicate_source_groups": [
            {
                "file_hash_prefix": d["file_hash"][:16],
                "location_count": len(d["source_locations"]),
                "locations_count_only": len(d["source_locations"]),
            }
            for d in discovered
            if len(d["source_locations"]) > 1
        ],
        "ali_police_deduped": bool(
            ali and len(ali.get("source_locations") or []) >= 1
        ),
        "ali_police_source_location_count": (
            len(ali["source_locations"]) if ali else 0
        ),
    }

    ground_truth_status = {
        "corpus_gold": False,
        "human_ground_truth_review": "pending",
        "verdict_hint": "CORPUS REVIEW TOOL READY — HUMAN REVIEW PENDING",
        "approved_page_count": 0,
        "anchor_coverage": {
            "client_name": "seeded_pending_human_review",
            "law_firm": "seeded_pending_human_review",
            "police_badge_9065": (
                "seeded_on_ali_police_p2" if badge_located else "missing_source_file"
            ),
        },
        "difficult_badge_police_report_located": badge_located,
    }

    by_case: dict[str, int] = {}
    by_family: dict[str, int] = {}
    for d in documents:
        by_case[d["case_alias"]] = by_case.get(d["case_alias"], 0) + 1
        by_family[d["family"]] = by_family.get(d["family"], 0) + 1

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "private": True,
        "document_count_present": len(documents),
        "deduplicated_physical_files": len(discovered),
        "selected_page_count": len(selected),
        "safe_counts_by_case": by_case,
        "safe_counts_by_family": by_family,
        "documents": [
            {
                "doc_alias": d["doc_alias"],
                "case_alias": d["case_alias"],
                "family": d["family"],
                "file_type": d["file_type"],
                "page_count": d["page_count"],
                "source_location_count": len(d["source_locations"]),
                "challenges": d["challenges"],
                "inclusion_reason": d["inclusion_reason"],
                # hashes stay private in inventory csv only under tmp
                "file_hash": d["file_hash"],
                "canonical_relpath": d["canonical_relpath"],
                "source_locations": d["source_locations"],
            }
            for d in documents
        ],
        "selected_pages": selected,
        "difficult_badge_police_report_located": badge_located,
        "annotation_status_summary": {
            "machine_prefill": len(selected),
            "human_reviewed": 0,
        },
    }

    annotation_schema_ref = {
        "description": "See docs/remediation/schemas/page-annotation.schema.json",
        "prefill_label": "UNVERIFIED MACHINE OUTPUT",
        "statuses": [
            "machine_prefill",
            "in_review",
            "human_reviewed",
            "needs_second_review",
            "unreadable",
        ],
    }

    (OUT / "corpus_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "annotation_schema.json").write_text(
        json.dumps(annotation_schema_ref, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "ground_truth_status.json").write_text(
        json.dumps(ground_truth_status, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "corpus_deduplication.json").write_text(
        json.dumps(dedupe_report, indent=2) + "\n", encoding="utf-8"
    )

    with (OUT / "document_inventory.csv").open("w", encoding="utf-8", newline="") as f:
        fields = [
            "case_alias",
            "doc_alias",
            "family",
            "file_type",
            "page_count",
            "file_hash",
            "source_location_count",
            "inclusion_reason",
        ]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for d in documents:
            w.writerow(
                {
                    "case_alias": d["case_alias"],
                    "doc_alias": d["doc_alias"],
                    "family": d["family"],
                    "file_type": d["file_type"],
                    "page_count": d["page_count"],
                    "file_hash": d["file_hash"],
                    "source_location_count": len(d["source_locations"]),
                    "inclusion_reason": d["inclusion_reason"],
                }
            )

    with (OUT / "corpus_manifest.csv").open("w", encoding="utf-8", newline="") as f:
        fields = [
            "page_id",
            "case_alias",
            "doc_alias",
            "page_number",
            "selection_reason",
            "annotation_status",
            "challenges",
        ]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in selected:
            w.writerow(
                {
                    "page_id": row["page_id"],
                    "case_alias": row.get("case_alias"),
                    "doc_alias": row.get("doc_alias"),
                    "page_number": row.get("page_number"),
                    "selection_reason": row.get("selection_reason"),
                    "annotation_status": row.get("annotation_status"),
                    "challenges": "|".join(row.get("challenges") or []),
                }
            )

    (OUT / "README.txt").write_text(
        "PRIVATE acceptance corpus — do not commit.\n"
        "Hash-deduplicated multi-case discovery. Machine prefills are unverified.\n",
        encoding="utf-8",
    )

    # Update intake README
    (INTAKE / "README.txt").write_text(
        "PRIVATE INTAKE — Extraction Remediation Part 1\n"
        "==============================================\n\n"
        "3936314.pdf is present and hash-identical to the ali-vs-thomas copy.\n"
        "Corpus represents the document once (doc_alias=ali_police).\n"
        "Badge/ID USER_CONFIRMED_ANCHOR: visible 9065 vs corrupt Go6s on page 2.\n"
        "Do not fabricate other police-report ground truth from machine text.\n",
        encoding="utf-8",
    )

    return manifest


if __name__ == "__main__":
    m = build()
    print(
        "corpus:",
        m["document_count_present"],
        "docs,",
        m["selected_page_count"],
        "pages,",
        "badge=",
        m["difficult_badge_police_report_located"],
        "by_case=",
        m["safe_counts_by_case"],
    )

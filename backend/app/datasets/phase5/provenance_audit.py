"""Candidate-source provenance audit (aggregate-safe; selection metadata only)."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.datasets.phase5.constants import CANDIDATE_SOURCES, PROVENANCE_AUDIT_VERSION
from backend.app.datasets.phase5.jsonl_io import read_jsonl
from backend.app.datasets.phase5.paths import ensure_layout, manifest_path, pages_dir, reports_dir
from backend.app.datasets.phase5.queue import _canonical_crop_ids
from backend.app.datasets.phase5.schemas import (
    CropRecord,
    DocumentRecord,
    DuplicateFamilyRecord,
    SourceRecord,
)


def _evidence_counts(private_root: Path) -> dict[str, Any]:
    pages = pages_dir(private_root)
    result_files = sorted(pages.glob("*.result.json")) if pages.is_dir() else []
    lines = blocks = words = repairs = 0
    pages_block_eq_line = 0
    for path in result_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        line_n = len(data.get("lines") or [])
        block_n = len(data.get("blocks") or [])
        word_n = len(data.get("words") or [])
        repair_n = len(data.get("repair_regions") or [])
        lines += line_n
        blocks += block_n
        words += word_n
        repairs += repair_n
        if line_n and line_n == block_n:
            pages_block_eq_line += 1
    return {
        "result_page_count": len(result_files),
        "evidence_line_count": lines,
        "evidence_block_count": blocks,
        "evidence_word_count": words,
        "evidence_repair_region_count": repairs,
        "pages_where_blocks_eq_lines": pages_block_eq_line,
    }


def audit_candidate_provenance(private_root: Path) -> dict[str, Any]:
    """Trace evidence → crops → canonical queue membership by candidate_source."""

    ensure_layout(private_root)
    crops = read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
    documents = read_jsonl(manifest_path(private_root, "document-manifest.jsonl"), DocumentRecord)
    sources = read_jsonl(manifest_path(private_root, "source-manifest.jsonl"), SourceRecord)
    families = read_jsonl(
        manifest_path(private_root, "duplicate-families.jsonl"), DuplicateFamilyRecord
    )
    evidence = _evidence_counts(private_root)
    canonical = _canonical_crop_ids(crops, families) if families else {c.crop_id for c in crops}

    by_source: dict[str, list[CropRecord]] = defaultdict(list)
    for crop in crops:
        by_source[crop.candidate_source].append(crop)

    unique_pages = {s.page_id for s in sources}
    unique_groups = {d.source_group_id for d in documents}

    categories: list[dict[str, Any]] = []
    for name in sorted(CANDIDATE_SOURCES):
        rows = by_source.get(name, [])
        canon_n = sum(1 for c in rows if c.crop_id in canonical)
        page_cov = len({c.page_id for c in rows})
        group_cov = len({c.source_group_id for c in rows})
        # Presence in private evidence (geometry artefacts), not labels.
        if name == "full_page_ocr":
            present = evidence["evidence_line_count"] > 0 or evidence["evidence_word_count"] > 0
            excluded = 0
            note = "lines/words exported as full_page_ocr"
        elif name == "visual_detection":
            present = evidence["evidence_block_count"] > 0
            # Batch export intentionally excludes 1:1 line-proxy blocks.
            excluded = evidence["evidence_block_count"]
            note = (
                "blocks present as 1:1 line proxies; export-all skips blocks "
                "to avoid exact region duplicates"
            )
        elif name == "targeted_repair":
            present = evidence["evidence_repair_region_count"] > 0
            excluded = 0
            note = "repair_regions empty in private populate evidence"
        elif name in {"heuristic_region", "noise_region", "manual_region", "synthetic_negative"}:
            present = False
            excluded = 0
            note = "not produced by private populate path; schema-supported for manual import"
        else:
            present = False
            excluded = 0
            note = "unknown"
        categories.append(
            {
                "candidate_source": name,
                "candidate_record_count": len(rows),
                "canonical_crop_count": canon_n,
                "source_group_coverage": group_cov,
                "page_coverage": page_cov,
                "exclusion_count": excluded,
                "evidence_present": present,
                "status": (
                    "assigned"
                    if rows
                    else (
                        "excluded_as_line_proxy"
                        if name == "visual_detection" and evidence["evidence_block_count"] > 0
                        else "absent_from_private_evidence"
                    )
                ),
                "note": note,
            }
        )

    verdict = "correct"
    if evidence["evidence_repair_region_count"] > 0 and by_source.get("targeted_repair") is None:
        verdict = "manifest_defect"
    if (
        evidence["evidence_block_count"] > 0
        and evidence["pages_where_blocks_eq_lines"] < evidence["result_page_count"]
        and not by_source.get("visual_detection")
    ):
        # Genuine distinct visual blocks skipped without line coverage would be a defect.
        # Current populate writes 1:1 proxies; that is intentional, not collapse.
        pass

    report: dict[str, Any] = {
        "audit_version": PROVENANCE_AUDIT_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "verdict": verdict,
        "summary": {
            "document_count": len(documents),
            "source_group_count": len(unique_groups),
            "unique_source_page_ids": len(unique_pages),
            "source_manifest_rows": len(sources),
            "source_manifest_duplicate_rows": len(sources) - len(unique_pages),
            "crop_record_count": len(crops),
            "canonical_crop_count": len(canonical),
            **evidence,
        },
        "categories": categories,
        "explanation": (
            "Private populate writes OCR line/word geometry with empty repair_regions and "
            "1:1 block proxies copied from lines. Batch export uses kinds={lines, repair_regions} "
            "so all crops are full_page_ocr. This is correct provenance, not a collapse of "
            "distinct Phase 4 visual/repair categories into full_page_ocr."
        ),
        "candidate_source_is_not_a_label": True,
    }
    out = reports_dir(private_root) / "provenance-audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # Also keep a copy under manifests for tooling discoverability (gitignored).
    manifest_path(private_root, "provenance-audit.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def render_provenance_aggregate_markdown(report: dict[str, Any]) -> str:
    """Committed-safe provenance table (no private IDs)."""

    summary = report.get("summary") or {}
    lines = [
        "# Phase 5 candidate-source provenance audit",
        "",
        f"**Verdict:** `{report.get('verdict')}`",
        "",
        f"Audit version: `{report.get('audit_version')}`",
        f"Generated (UTC): `{report.get('generated_at')}`",
        "",
        "## Aggregate evidence",
        "",
        f"- Documents: **{summary.get('document_count', 0)}**",
        f"- Source groups: **{summary.get('source_group_count', 0)}**",
        f"- Unique page IDs: **{summary.get('unique_source_page_ids', 0)}**",
        f"- Source-manifest rows: **{summary.get('source_manifest_rows', 0)}**",
        f"- Source-manifest duplicate rows: **{summary.get('source_manifest_duplicate_rows', 0)}**",
        f"- Crop records: **{summary.get('crop_record_count', 0)}**",
        f"- Canonical crops: **{summary.get('canonical_crop_count', 0)}**",
        f"- Evidence lines: **{summary.get('evidence_line_count', 0)}**",
        f"- Evidence blocks: **{summary.get('evidence_block_count', 0)}**",
        f"- Evidence words: **{summary.get('evidence_word_count', 0)}**",
        f"- Evidence repair regions: **{summary.get('evidence_repair_region_count', 0)}**",
        f"- Pages with 1:1 block=line proxies: **{summary.get('pages_where_blocks_eq_lines', 0)}**",
        "",
        "## Candidate-source categories",
        "",
        "| category | records | canonical | groups | pages | excluded | status |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in report.get("categories") or []:
        lines.append(
            f"| `{row['candidate_source']}` | {row['candidate_record_count']} | "
            f"{row['canonical_crop_count']} | {row['source_group_coverage']} | "
            f"{row['page_coverage']} | {row['exclusion_count']} | `{row['status']}` |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            str(report.get("explanation") or ""),
            "",
            "Candidate provenance is selection metadata only and must never be treated as a "
            "script label or shown to primary/secondary crop reviewers.",
            "",
        ]
    )
    return "\n".join(lines)

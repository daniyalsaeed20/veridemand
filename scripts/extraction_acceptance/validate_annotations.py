"""Validate private annotations and emit private progress reports."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from extraction_acceptance.gitignore_guard import assert_private_paths_ignored
from extraction_acceptance.review_app.annotation_store import (
    AnnotationStore,
    can_mark_human_reviewed,
    validate_annotation,
    validate_polygon,
)

CORPUS = ROOT / "tmp" / "extraction-remediation" / "acceptance-corpus"
REVIEW = ROOT / "tmp" / "extraction-remediation" / "acceptance-review"
REPORTS = ROOT / "tmp" / "extraction-remediation" / "reports"


def run() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((CORPUS / "corpus_manifest.json").read_text(encoding="utf-8"))
    store = AnnotationStore(REVIEW)
    selected = manifest.get("selected_pages") or []

    progress = {
        "machine_prefill": 0,
        "in_review": 0,
        "human_reviewed": 0,
        "needs_second_review": 0,
        "unreadable": 0,
        "missing_annotation": 0,
    }
    completeness_issues: list[dict] = []
    critical_report: list[dict] = []
    gt_ready = 0

    for page in selected:
        page_id = page["page_id"]
        path = store.pages_dir / page_id / "annotation.json"
        if not path.is_file():
            progress["missing_annotation"] += 1
            completeness_issues.append({"page_id": page_id, "issue": "missing_annotation"})
            continue
        ann = json.loads(path.read_text(encoding="utf-8"))
        st = ann.get("annotation_status") or "machine_prefill"
        progress[st] = progress.get(st, 0) + 1

        errors = validate_annotation(ann)
        if errors:
            completeness_issues.append({"page_id": page_id, "issue": "schema", "errors": errors})

        # Machine prefill preserved
        if "machine_transcript" not in ann:
            completeness_issues.append({"page_id": page_id, "issue": "missing_machine_transcript"})
        if ann.get("expected_transcript") is None:
            completeness_issues.append({"page_id": page_id, "issue": "missing_expected_transcript_field"})

        for box in ann.get("expected_boxes") or []:
            pe = validate_polygon(box.get("polygon"))
            if pe:
                completeness_issues.append({"page_id": page_id, "issue": "bad_polygon", "detail": pe})

        for field in ann.get("critical_fields") or []:
            critical_report.append(
                {
                    "page_id": page_id,
                    "field_id": field.get("field_id"),
                    "status": field.get("status"),
                    "match_status": field.get("match_status"),
                    "has_expected": bool(field.get("expected")),
                    # no expected values in aggregate beyond presence
                }
            )

        if st == "human_reviewed":
            ok, blockers = can_mark_human_reviewed(ann)
            if not ok:
                completeness_issues.append(
                    {"page_id": page_id, "issue": "approved_incomplete", "blockers": blockers}
                )
            elif ann.get("ground_truth_ready"):
                gt_ready += 1

    dedupe = {}
    dedupe_path = CORPUS / "corpus_deduplication.json"
    if dedupe_path.is_file():
        dedupe = json.loads(dedupe_path.read_text(encoding="utf-8"))

    ignore_failures = assert_private_paths_ignored(
        [
            "tmp/extraction-remediation",
            "tmp/extraction-remediation/acceptance-review",
            "docs/example/ali-vs-thomas/3936314.pdf",
        ]
    )

    # Duplicate page check by (doc_alias, page_number)
    seen = set()
    dup_pages = []
    for page in selected:
        key = (page.get("doc_alias"), page.get("page_number"))
        if key in seen:
            dup_pages.append(page.get("page_id"))
        seen.add(key)

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selected_page_count": len(selected),
        "review_progress": progress,
        "completeness_issue_count": len(completeness_issues),
        "critical_anchor_rows": len(critical_report),
        "ground_truth_ready_pages": gt_ready,
        "corpus_gold": False,
        "duplicate_benchmark_pages": dup_pages,
        "deduplication_summary": {
            "discovered_file_count": dedupe.get("discovered_file_count"),
            "ali_police_source_location_count": dedupe.get("ali_police_source_location_count"),
        },
        "gitignore_failures": ignore_failures,
        "verdict": "CORPUS REVIEW TOOL READY — HUMAN REVIEW PENDING",
    }

    (REPORTS / "review_progress.json").write_text(
        json.dumps({"progress": progress, "selected": len(selected)}, indent=2) + "\n",
        encoding="utf-8",
    )
    (REPORTS / "annotation_completeness.json").write_text(
        json.dumps({"issues": completeness_issues}, indent=2) + "\n", encoding="utf-8"
    )
    (REPORTS / "critical_anchor_report.json").write_text(
        json.dumps({"rows": critical_report}, indent=2) + "\n", encoding="utf-8"
    )
    (REPORTS / "ground_truth_readiness.json").write_text(
        json.dumps(
            {
                "corpus_gold": False,
                "ground_truth_ready_pages": gt_ready,
                "human_reviewed": progress.get("human_reviewed", 0),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (REPORTS / "validation_summary.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    r = run()
    print("validation:", r["verdict"], "issues=", r["completeness_issue_count"])

"""Dataset readiness reporting (private detailed + committed aggregate)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.datasets.phase5.constants import CROP_PADDING_VERSION, SCHEMA_VERSION
from backend.app.datasets.phase5.jsonl_io import read_jsonl
from backend.app.datasets.phase5.paths import manifest_path, reports_dir
from backend.app.datasets.phase5.schemas import (
    CropRecord,
    DocumentRecord,
    PilotManifest,
    ResolvedLabelRecord,
    ReviewEvent,
    ReviewQueueManifest,
    SplitManifest,
)


def _suppress_small_strata(counts: dict[str, int], *, min_count: int = 2) -> dict[str, int]:
    """Merge singleton strata into other for committed privacy safety."""

    out: dict[str, int] = {}
    other = 0
    for key, value in counts.items():
        if value < min_count:
            other += value
        else:
            out[key] = value
    if other:
        out["other"] = out.get("other", 0) + other
    return out


def build_readiness(private_root: Path) -> dict[str, Any]:
    crops = read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
    events = read_jsonl(manifest_path(private_root, "review-events.jsonl"), ReviewEvent)
    resolved = read_jsonl(manifest_path(private_root, "resolved-labels.jsonl"), ResolvedLabelRecord)
    splits = read_jsonl(manifest_path(private_root, "split-manifest.jsonl"), SplitManifest)
    documents = read_jsonl(manifest_path(private_root, "document-manifest.jsonl"), DocumentRecord)
    queues = read_jsonl(
        manifest_path(private_root, "primary-review-queue.jsonl"), ReviewQueueManifest
    )
    pilots = read_jsonl(manifest_path(private_root, "pilot-manifest.jsonl"), PilotManifest)
    pilot = pilots[-1] if pilots else None

    status_counts = Counter(r.status for r in resolved)
    label_counts = Counter(r.label for r in resolved if r.label)
    training_eligible = sum(1 for r in resolved if r.training_eligible)
    cand_counts = Counter(c.candidate_source for c in crops)
    family_counts: dict[str, int] = dict(Counter(str(d.source_family) for d in documents))
    queue = queues[-1] if queues else None
    worklist_path = reports_dir(private_root) / "manual-region-worklist.jsonl"
    manual_pages = 0
    if worklist_path.is_file():
        manual_pages = sum(
            1 for line in worklist_path.read_text(encoding="utf-8").splitlines() if line.strip()
        )

    unreviewed = len(crops) - sum(1 for r in resolved if r.status not in {"unreviewed", None})
    if not resolved:
        unreviewed = len(crops)

    status_line = "PRIVATE CORPUS POPULATED — COVERAGE AND ANNOTATION PILOT REQUIRED"
    if pilot and pilot.crop_count > 0:
        status_line = "PRIVATE CORPUS POPULATED — COVERAGE AND ANNOTATION PILOT REQUIRED"

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "status_line": status_line,
        "schema_version": SCHEMA_VERSION,
        "crop_padding_version": CROP_PADDING_VERSION,
        "document_count": len(documents),
        "source_group_count": len({d.source_group_id for d in documents}),
        "crop_count": len(crops),
        "unreviewed_count": unreviewed,
        "review_event_count": len(events),
        "resolved_count": len(resolved),
        "training_eligible_count": training_eligible,
        "resolution_status_counts": dict(status_counts),
        "label_counts": {k: v for k, v in label_counts.items() if k is not None},
        "candidate_source_counts": dict(cand_counts),
        "source_family_counts": _suppress_small_strata(family_counts),
        "split_manifest_present": bool(splits),
        "held_out_frozen": bool(
            splits and any(a.split == "held_out" for a in splits[-1].assignments)
        ),
        "queue_present": queue is not None,
        "queue_version": queue.queue_version if queue else None,
        "queue_seed": queue.seed if queue else None,
        "queue_sha256": queue.content_sha256 if queue else None,
        "queue_crop_count": len(queue.entries) if queue else 0,
        "queue_authorised_for_review": bool(queue.authorised_for_review) if queue else False,
        "manual_region_worklist_pages": manual_pages,
        "manual_region_status": "not_yet_human_verified",
        "pilot_present": pilot is not None,
        "pilot_crop_count": pilot.crop_count if pilot else 0,
        "pilot_version": pilot.pilot_version if pilot else None,
        "pilot_sha256": pilot.content_sha256 if pilot else None,
        "training_authorised": False,
        "notes": [
            "Human labels are required; OCR/heuristic predictions are never ground truth.",
            "No classifier training is authorised yet.",
            "Default labelling uses pilot-primary / pilot-secondary until pilot approval.",
            "Full primary queue is preserved but not authorised for review until pilot approval.",
            "Manual-region requirement: not yet human-verified.",
            "Committed aggregate reports must use opaque counts only (no paths/text).",
        ],
    }


def write_private_report(private_root: Path) -> Path:
    report = build_readiness(private_root)
    out_dir = reports_dir(private_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "readiness.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


def render_committed_aggregate_markdown(report: dict[str, Any]) -> str:
    """Privacy-safe aggregate markdown for docs/evaluation/."""

    labels: dict[str, Any] = report.get("label_counts") or {}
    statuses: dict[str, Any] = report.get("resolution_status_counts") or {}
    cands: dict[str, Any] = report.get("candidate_source_counts") or {}
    families: dict[str, Any] = report.get("source_family_counts") or {}
    lines = [
        "# Phase 5 dataset readiness",
        "",
        f"**Status:** {report.get('status_line')}",
        "",
        f"Generated (UTC): `{report.get('generated_at')}`",
        "",
        "## Aggregate counts (opaque)",
        "",
        f"- Schema version: `{report.get('schema_version')}`",
        f"- Crop padding version: `{report.get('crop_padding_version')}`",
        f"- Documents registered: **{report.get('document_count', 0)}**",
        f"- Source groups: **{report.get('source_group_count', 0)}**",
        f"- Crops in private manifest: **{report.get('crop_count', 0)}**",
        f"- Unreviewed crops: **{report.get('unreviewed_count', 0)}**",
        f"- Review events: **{report.get('review_event_count', 0)}**",
        f"- Resolved records: **{report.get('resolved_count', 0)}**",
        f"- Training-eligible (3-class agreed/adjudicated): "
        f"**{report.get('training_eligible_count', 0)}**",
        f"- Primary queue crops: **{report.get('queue_crop_count', 0)}**",
        f"- Queue version: `{report.get('queue_version')}`",
        f"- Queue seed: `{report.get('queue_seed')}`",
        f"- Queue SHA-256: `{report.get('queue_sha256')}`",
        f"- Queue authorised: **{report.get('queue_authorised_for_review', False)}**",
        f"- Pilot crop count: **{report.get('pilot_crop_count', 0)}**",
        f"- Pilot version: `{report.get('pilot_version')}`",
        f"- Pilot SHA-256: `{report.get('pilot_sha256')}`",
        f"- Manual-region worklist pages: **{report.get('manual_region_worklist_pages', 0)}**",
        (
            f"- Manual-region requirement: "
            f"**{report.get('manual_region_status', 'not_yet_human_verified')}**"
        ),
        f"- Split manifest present: **{report.get('split_manifest_present', False)}**",
        f"- Held-out frozen: **{report.get('held_out_frozen', False)}**",
        f"- Classifier training authorised: **{report.get('training_authorised', False)}**",
        "",
        "### Candidate-source coverage",
        "",
    ]
    if cands:
        for key, value in sorted(cands.items()):
            lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- _(none)_")
    lines.extend(["", "### Broad source-family coverage", ""])
    if families:
        for key, value in sorted(families.items()):
            lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- _(none)_")
    lines.extend(["", "### Resolution status", ""])
    if statuses:
        for key, value in sorted(statuses.items()):
            lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- _(none — primary human review pending)_")
    lines.extend(["", "### Human labels", ""])
    if labels:
        for key, value in sorted(labels.items()):
            lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- _(none — expect zeros until private labelling)_")
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- Labels are human-only (`printed` / `handwritten` / `uncertain` / `non_text`).",
            "- Signatures are labelled `handwritten`.",
            "- `uncertain` is excluded from initial 3-class training.",
            "- No classifier training is authorised yet.",
            "- Default human review uses `pilot-primary` until the annotation pilot is approved.",
            "- Full primary queue is preserved but not authorised until pilot approval.",
            "- Manual-region requirement: not yet human-verified.",
            "- Splits are not generated until labels exist.",
            "- Private crops, paths, and transcripts are never committed.",
            "",
            "See `docs/datasets/phase-5-handwriting-dataset.md`, "
            "`docs/evaluation/phase-5-annotation-pilot.md`, and ADR 0052.",
            "",
        ]
    )
    return "\n".join(lines)

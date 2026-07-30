"""Dataset readiness reporting (private detailed + committed aggregate)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.datasets.phase5.jsonl_io import read_jsonl
from backend.app.datasets.phase5.paths import manifest_path, reports_dir
from backend.app.datasets.phase5.schemas import (
    CropRecord,
    ResolvedLabelRecord,
    ReviewEvent,
    SplitManifest,
)


def build_readiness(private_root: Path) -> dict[str, Any]:
    crops = read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
    events = read_jsonl(manifest_path(private_root, "review-events.jsonl"), ReviewEvent)
    resolved = read_jsonl(manifest_path(private_root, "resolved-labels.jsonl"), ResolvedLabelRecord)
    splits = read_jsonl(manifest_path(private_root, "split-manifest.jsonl"), SplitManifest)

    status_counts = Counter(r.status for r in resolved)
    label_counts = Counter(r.label for r in resolved if r.label)
    training_eligible = sum(1 for r in resolved if r.training_eligible)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "status_line": "DATASET TOOLING READY — HUMAN LABELLING REQUIRED",
        "crop_count": len(crops),
        "review_event_count": len(events),
        "resolved_count": len(resolved),
        "training_eligible_count": training_eligible,
        "resolution_status_counts": dict(status_counts),
        "label_counts": {k: v for k, v in label_counts.items() if k is not None},
        "split_manifest_present": bool(splits),
        "held_out_frozen": bool(
            splits and any(a.split == "held_out" for a in splits[-1].assignments)
        ),
        "notes": [
            "Human labels are required; OCR/heuristic predictions are never ground truth.",
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
    lines = [
        "# Phase 5 dataset readiness",
        "",
        f"**Status:** {report.get('status_line')}",
        "",
        f"Generated (UTC): `{report.get('generated_at')}`",
        "",
        "## Aggregate counts (opaque)",
        "",
        f"- Crops in private manifest: **{report.get('crop_count', 0)}**",
        f"- Review events: **{report.get('review_event_count', 0)}**",
        f"- Resolved records: **{report.get('resolved_count', 0)}**",
        f"- Training-eligible (3-class agreed/adjudicated): "
        f"**{report.get('training_eligible_count', 0)}**",
        f"- Split manifest present: **{report.get('split_manifest_present', False)}**",
        f"- Held-out frozen: **{report.get('held_out_frozen', False)}**",
        "",
        "### Resolution status",
        "",
    ]
    if statuses:
        for key, value in sorted(statuses.items()):
            lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- _(none — human labelling not started)_")
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
            "- Splits are group-aware (`source_group_id` + `duplicate_family_id`).",
            "- Private crops, paths, and transcripts are never committed.",
            "",
            "See `docs/datasets/phase-5-handwriting-dataset.md` and ADR 0051.",
            "",
        ]
    )
    return "\n".join(lines)

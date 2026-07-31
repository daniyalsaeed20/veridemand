"""Pilot agreement reporting (computed only after real human reviews)."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from backend.app.datasets.phase5.constants import HUMAN_LABELS
from backend.app.datasets.phase5.jsonl_io import read_jsonl
from backend.app.datasets.phase5.paths import manifest_path
from backend.app.datasets.phase5.schemas import CropRecord, PilotManifest, ReviewEvent


def cohens_kappa(labels_a: list[str], labels_b: list[str]) -> float | None:
    """Cohen's kappa for paired categorical labels; None if undefined."""

    if len(labels_a) != len(labels_b) or not labels_a:
        return None
    cats = sorted(set(labels_a) | set(labels_b))
    n = len(labels_a)
    matrix = {(i, j): 0 for i in cats for j in cats}
    for a, b in zip(labels_a, labels_b, strict=True):
        matrix[(a, b)] += 1
    po = sum(matrix[(c, c)] for c in cats) / n
    pa = Counter(labels_a)
    pb = Counter(labels_b)
    pe = sum((pa[c] / n) * (pb[c] / n) for c in cats)
    if abs(1.0 - pe) < 1e-12:
        # Undefined when expected agreement is 1 (e.g. single class both sides).
        return None
    return (po - pe) / (1.0 - pe)


def build_pilot_agreement_report(private_root: Path) -> dict[str, Any]:
    """Aggregate agreement metrics from real review events on pilot crops only."""

    pilots = read_jsonl(manifest_path(private_root, "pilot-manifest.jsonl"), PilotManifest)
    if not pilots:
        return {"status": "no_pilot", "primary_completed": 0, "secondary_completed": 0}
    pilot = pilots[-1]
    pilot_ids = {e.canonical_crop_id for e in pilot.entries}
    crops = {
        c.crop_id: c
        for c in read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
        if c.crop_id in pilot_ids
    }
    events = read_jsonl(manifest_path(private_root, "review-events.jsonl"), ReviewEvent)

    primary: dict[str, str] = {}
    secondary: dict[str, str] = {}
    primary_excl: set[str] = set()
    secondary_excl: set[str] = set()
    quality_flags: Counter[str] = Counter()
    uncertain_by_role: Counter[str] = Counter()
    exclude_by_role: Counter[str] = Counter()

    for ev in events:
        if ev.crop_id not in pilot_ids:
            continue
        crop = crops.get(ev.crop_id)
        if crop is None or ev.crop_sha256 != crop.sha256:
            continue
        for flag in ev.quality_flags:
            quality_flags[flag] += 1
        if ev.action == "exclude":
            exclude_by_role[ev.role] += 1
            if ev.role == "primary":
                primary_excl.add(ev.crop_id)
            elif ev.role == "secondary":
                secondary_excl.add(ev.crop_id)
            continue
        if ev.action == "label" and ev.label is not None:
            if ev.label == "uncertain":
                uncertain_by_role[ev.role] += 1
            if ev.role == "primary":
                primary[ev.crop_id] = ev.label
            elif ev.role == "secondary":
                secondary[ev.crop_id] = ev.label

    paired_ids = sorted(set(primary) & set(secondary))
    labels_a = [primary[i] for i in paired_ids]
    labels_b = [secondary[i] for i in paired_ids]
    agree = sum(1 for a, b in zip(labels_a, labels_b, strict=True) if a == b)
    raw_agreement = (agree / len(paired_ids)) if paired_ids else None

    per_label: dict[str, dict[str, int]] = {
        lab: {"agree": 0, "primary_only": 0, "secondary_only": 0} for lab in sorted(HUMAN_LABELS)
    }
    confusion: dict[str, dict[str, int]] = {
        a: {b: 0 for b in sorted(HUMAN_LABELS)} for a in sorted(HUMAN_LABELS)
    }
    for a, b in zip(labels_a, labels_b, strict=True):
        confusion[a][b] += 1
        if a == b:
            per_label[a]["agree"] += 1
        else:
            per_label[a]["primary_only"] += 1
            per_label[b]["secondary_only"] += 1

    conflicts = sum(1 for a, b in zip(labels_a, labels_b, strict=True) if a != b)
    excl_conflicts = len(primary_excl.symmetric_difference(secondary_excl))

    by_cand: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for cid in paired_ids:
        crop = crops[cid]
        by_cand[crop.candidate_source].append((primary[cid], secondary[cid]))
    agreement_by_candidate = {
        src: (sum(1 for a, b in pairs if a == b) / len(pairs) if pairs else None)
        for src, pairs in by_cand.items()
    }

    return {
        "status": "ok" if paired_ids else "awaiting_dual_reviews",
        "primary_completed": len(primary) + len(primary_excl),
        "secondary_completed": len(secondary) + len(secondary_excl),
        "paired_label_count": len(paired_ids),
        "raw_agreement": raw_agreement,
        "per_label_agreement": per_label,
        "confusion_matrix": confusion,
        "conflict_count": conflicts,
        "exclusion_conflict_count": excl_conflicts,
        "uncertain_rate_by_reviewer": dict(uncertain_by_role),
        "exclusion_rate_by_reviewer": dict(exclude_by_role),
        "quality_flag_counts": dict(quality_flags),
        "agreement_by_candidate_source": agreement_by_candidate,
        "cohens_kappa": cohens_kappa(labels_a, labels_b),
        "adjudication_count": 0,
        "note": "No fabricated agreement; values reflect real review events only.",
    }

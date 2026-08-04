"""Private training-manifest construction (opaque references only)."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from backend.app.datasets.phase5.jsonl_io import read_jsonl
from backend.app.datasets.phase5.paths import (
    crops_dir,
    default_private_root,
    manifest_path,
)
from backend.app.datasets.phase5.schemas import (
    CropRecord,
    HandwritingSeedRecord,
    ResolvedLabelRecord,
)

from model_development.handwriting_classifier.config import CLASS_ORDER

LabelSource = Literal["prototype_primary_review", "human_confirmed_handwriting_seed"]
ModelLabel = Literal["printed", "handwritten", "non_text"]


@dataclass(frozen=True)
class TrainingExample:
    schema_version: str
    training_manifest_version: str
    crop_id: str
    crop_sha256: str
    source_group_id: str
    label: ModelLabel
    label_source: LabelSource
    review_status: str
    crop_path_private: str
    width: int
    height: int
    source_category: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def _canonical_jsonl(rows: list[dict[str, Any]]) -> bytes:
    lines = [json.dumps(r, sort_keys=True, separators=(",", ":")) for r in rows]
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


def build_training_manifest(
    private_root: Path | None = None,
    *,
    require_crop_files: bool = True,
) -> tuple[list[TrainingExample], list[TrainingExample], dict[str, Any]]:
    """Build fit + uncertain-challenge manifests from human-reviewed private data.

    Uncertain / excluded never enter the fit set.
    Exact crop SHA duplicates contribute one canonical example.
    """

    root = private_root or default_private_root()
    crops = {
        c.crop_id: c for c in read_jsonl(manifest_path(root, "crop-manifest.jsonl"), CropRecord)
    }
    resolved = read_jsonl(manifest_path(root, "resolved-labels.jsonl"), ResolvedLabelRecord)
    seeds = read_jsonl(manifest_path(root, "handwriting-seed-records.jsonl"), HandwritingSeedRecord)

    fit_by_sha: dict[str, TrainingExample] = {}
    challenge_by_sha: dict[str, TrainingExample] = {}
    rejected: Counter[str] = Counter()

    for row in resolved:
        if row.label == "uncertain":
            crop = crops.get(row.crop_id)
            if crop is None:
                rejected["uncertain_missing_crop"] += 1
                continue
            path = root / crop.crop_relpath
            if require_crop_files and not path.is_file():
                rejected["uncertain_missing_file"] += 1
                continue
            ex = TrainingExample(
                schema_version="phase5-classifier-training-schema-v1",
                training_manifest_version="phase5-classifier-training-manifest-v1",
                crop_id=crop.crop_id,
                crop_sha256=crop.sha256,
                source_group_id=crop.source_group_id,
                label="printed",  # placeholder unused for challenge GT
                label_source="prototype_primary_review",
                review_status=row.status,
                crop_path_private=str(path),
                width=crop.width_px,
                height=crop.height_px,
                source_category="uncertain_challenge",
            )
            # Store as challenge with original label encoded in source_category.
            challenge_by_sha.setdefault(crop.sha256, ex)
            continue

        if not row.prototype_model_eligible:
            rejected["not_prototype_eligible"] += 1
            continue
        if row.label not in ("printed", "non_text"):
            rejected["ineligible_label"] += 1
            continue
        crop = crops.get(row.crop_id)
        if crop is None:
            rejected["missing_crop"] += 1
            continue
        if crop.sha256 != row.crop_sha256:
            rejected["stale_hash"] += 1
            continue
        path = root / crop.crop_relpath
        if require_crop_files and not path.is_file():
            rejected["missing_file"] += 1
            continue
        ex = TrainingExample(
            schema_version="phase5-classifier-training-schema-v1",
            training_manifest_version="phase5-classifier-training-manifest-v1",
            crop_id=crop.crop_id,
            crop_sha256=crop.sha256,
            source_group_id=crop.source_group_id,
            label=row.label,  # type: ignore[arg-type]
            label_source="prototype_primary_review",
            review_status=row.status,
            crop_path_private=str(path),
            width=crop.width_px,
            height=crop.height_px,
            source_category=None,
        )
        if crop.sha256 in fit_by_sha:
            rejected["exact_duplicate"] += 1
            continue
        fit_by_sha[crop.sha256] = ex

    for seed in seeds:
        if seed.status != "active":
            rejected["seed_inactive"] += 1
            continue
        crop = crops.get(seed.crop_id)
        if crop is None:
            rejected["seed_missing_crop"] += 1
            continue
        if crop.sha256 != seed.crop_sha256:
            rejected["seed_stale_hash"] += 1
            continue
        path = root / crop.crop_relpath
        if require_crop_files and not path.is_file():
            rejected["seed_missing_file"] += 1
            continue
        ex = TrainingExample(
            schema_version="phase5-classifier-training-schema-v1",
            training_manifest_version="phase5-classifier-training-manifest-v1",
            crop_id=crop.crop_id,
            crop_sha256=crop.sha256,
            source_group_id=crop.source_group_id,
            label="handwritten",
            label_source="human_confirmed_handwriting_seed",
            review_status="active_seed",
            crop_path_private=str(path),
            width=crop.width_px,
            height=crop.height_px,
            source_category=",".join(seed.categories) if seed.categories else None,
        )
        if crop.sha256 in fit_by_sha:
            rejected["seed_exact_duplicate"] += 1
            continue
        fit_by_sha[crop.sha256] = ex

    fit = sorted(fit_by_sha.values(), key=lambda e: (e.source_group_id, e.crop_id))
    # Rebuild challenge with label marker — use source_category=uncertain_challenge
    challenge = sorted(challenge_by_sha.values(), key=lambda e: (e.source_group_id, e.crop_id))

    counts = Counter(e.label for e in fit)
    groups = sorted({e.source_group_id for e in fit})
    hw_groups = sorted({e.source_group_id for e in fit if e.label == "handwritten"})
    summary: dict[str, Any] = {
        "printed": counts.get("printed", 0),
        "handwritten": counts.get("handwritten", 0),
        "non_text": counts.get("non_text", 0),
        "uncertain_challenge": len(challenge),
        "source_group_count": len(groups),
        "handwriting_source_group_count": len(hw_groups),
        "rejected": dict(rejected),
        "class_order": list(CLASS_ORDER),
    }
    return fit, challenge, summary


def write_private_manifest(
    examples: list[TrainingExample],
    path: Path,
) -> str:
    """Write private JSONL and return SHA-256 of canonical bytes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [e.to_dict() for e in examples]
    # Strip absolute paths from committed-safe hash by hashing without path? No —
    # private hash includes private paths; never leave the private tree.
    payload = _canonical_jsonl(rows)
    path.write_bytes(payload)
    return _sha256_bytes(payload)


def write_deferred_held_out_manifest(path: Path) -> str:
    """Document that no release held-out set is frozen for Task B."""

    rows = [
        {
            "schema_version": "phase5-classifier-training-schema-v1",
            "held_out_authorised": False,
            "crop_ids": [],
            "notes": (
                "Task B prototype: release held-out is not frozen. "
                "This placeholder satisfies package schema hashing only."
            ),
        }
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_jsonl(rows)
    path.write_bytes(payload)
    return _sha256_bytes(payload)


def aggregate_is_expected(summary: dict[str, Any]) -> tuple[bool, str]:
    """Soft check against Task B expected aggregates."""

    expected = {
        "printed": 221,
        "handwritten": 55,
        "non_text": 23,
        "uncertain_challenge": 54,
        "source_group_count": 6,
        "handwriting_source_group_count": 3,
    }
    mismatches = []
    for key, want in expected.items():
        got = summary.get(key)
        if got != want:
            mismatches.append(f"{key}: expected {want}, got {got}")
    if mismatches:
        return False, "; ".join(mismatches)
    return True, "ok"


def source_groups(examples: list[TrainingExample]) -> list[str]:
    return sorted({e.source_group_id for e in examples})


def filter_by_groups(examples: list[TrainingExample], groups: set[str]) -> list[TrainingExample]:
    return [e for e in examples if e.source_group_id in groups]


def class_counts(examples: list[TrainingExample]) -> dict[str, int]:
    c = Counter(e.label for e in examples)
    return {lab: int(c.get(lab, 0)) for lab in CLASS_ORDER}


def crops_root_hint(private_root: Path | None = None) -> Path:
    return crops_dir(private_root or default_private_root())

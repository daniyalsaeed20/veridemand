"""Duplicate detection and group-aware dataset splits."""

from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from backend.app.datasets.phase5.constants import (
    PERCEPTUAL_HAMMING_WARN_THRESHOLD,
    SPLIT_ALGORITHM_VERSION,
)
from backend.app.datasets.phase5.hashes import hamming_hex
from backend.app.datasets.phase5.ids import new_duplicate_family_id
from backend.app.datasets.phase5.jsonl_io import read_jsonl, write_jsonl_atomic
from backend.app.datasets.phase5.paths import manifest_path
from backend.app.datasets.phase5.schemas import (
    CropRecord,
    DuplicateFamilyRecord,
    ResolvedLabelRecord,
    SplitAssignment,
    SplitManifest,
    SplitName,
)


def _now() -> datetime:
    return datetime.now(UTC)


def build_duplicate_families(
    crops: list[CropRecord],
) -> tuple[list[DuplicateFamilyRecord], list[str]]:
    """Exact SHA-256 families; perceptual near-dup warnings (non-binding)."""

    by_sha: dict[str, list[CropRecord]] = defaultdict(list)
    for crop in crops:
        by_sha[crop.sha256].append(crop)

    families: list[DuplicateFamilyRecord] = []
    sha_to_family: dict[str, str] = {}
    for sha, members in sorted(by_sha.items()):
        fam_id = new_duplicate_family_id()
        sha_to_family[sha] = fam_id
        families.append(
            DuplicateFamilyRecord(
                duplicate_family_id=fam_id,
                sha256=sha,
                crop_ids=[m.crop_id for m in members],
            )
        )

    warnings: list[str] = []
    # Bucket by perceptual-hash prefix so near-dup checks stay tractable at scale.
    by_phash: dict[str, list[CropRecord]] = defaultdict(list)
    for crop in crops:
        by_phash[crop.perceptual_hash[:8]].append(crop)
    warn_cap = 1000
    for bucket in by_phash.values():
        if len(warnings) >= warn_cap:
            break
        for i, a in enumerate(bucket):
            if len(warnings) >= warn_cap:
                break
            for b in bucket[i + 1 :]:
                if a.sha256 == b.sha256:
                    continue
                dist = hamming_hex(a.perceptual_hash, b.perceptual_hash)
                if dist <= PERCEPTUAL_HAMMING_WARN_THRESHOLD:
                    warnings.append(
                        f"perceptual near-duplicate warning: {a.crop_id} ~ {b.crop_id} "
                        f"(hamming={dist})"
                    )
                    if len(warnings) >= warn_cap:
                        break

    # Stamp family ids onto crop records for callers / rewrite.
    for i, crop in enumerate(crops):
        crops[i] = crop.model_copy(update={"duplicate_family_id": sha_to_family[crop.sha256]})

    return families, warnings


def _group_key(crop: CropRecord) -> str:
    fam = crop.duplicate_family_id or crop.sha256
    return f"{crop.source_group_id}|{fam}"


def group_aware_split(
    *,
    crops: list[CropRecord],
    resolved: list[ResolvedLabelRecord],
    seed: int,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    require_training_eligible: bool = True,
) -> SplitManifest:
    """Split by source_group_id + duplicate_family_id; byte-identical for same seed."""

    if abs(train_ratio + val_ratio + test_ratio - 1.0) > 1e-9:
        raise ValueError("split ratios must sum to 1.0")

    resolved_by_id = {r.crop_id: r for r in resolved}
    eligible: list[CropRecord] = []
    for crop in crops:
        res = resolved_by_id.get(crop.crop_id)
        if require_training_eligible and (res is None or not res.training_eligible):
            continue
        eligible.append(crop)

    if not eligible:
        raise ValueError(
            "No training-eligible crops for split "
            "(need agreed/adjudicated printed|handwritten|non_text labels)"
        )

    # Class support check
    labels = [
        resolved_by_id[c.crop_id].label
        for c in eligible
        if resolved_by_id.get(c.crop_id) and resolved_by_id[c.crop_id].label
    ]
    for needed in ("printed", "handwritten", "non_text"):
        if needed not in labels:
            raise ValueError(f"class-support failure: no eligible '{needed}' crops")

    groups: dict[str, list[CropRecord]] = defaultdict(list)
    for crop in eligible:
        groups[_group_key(crop)].append(crop)

    group_ids = sorted(groups.keys())
    rng = random.Random(seed)
    rng.shuffle(group_ids)

    n = len(group_ids)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)
    # Remainder → test to avoid empty due to flooring when n small.
    train_g = set(group_ids[:n_train])
    val_g = set(group_ids[n_train : n_train + n_val])
    test_g = set(group_ids[n_train + n_val :])
    if n >= 3 and (not train_g or not val_g or not test_g):
        # Ensure each split gets at least one group when possible.
        ordered = group_ids[:]
        train_g = {ordered[0]}
        val_g = {ordered[1]}
        test_g = {ordered[2]}
        for g in ordered[3:]:
            bucket = rng.random()
            if bucket < train_ratio:
                train_g.add(g)
            elif bucket < train_ratio + val_ratio:
                val_g.add(g)
            else:
                test_g.add(g)

    assignments: list[SplitAssignment] = []
    for gid, members in sorted(groups.items()):
        if gid in train_g:
            split: SplitName = "train"
        elif gid in val_g:
            split = "val"
        else:
            split = "test"
        for crop in members:
            assignments.append(
                SplitAssignment(
                    crop_id=crop.crop_id,
                    split=split,
                    source_group_id=crop.source_group_id,
                    duplicate_family_id=crop.duplicate_family_id,
                )
            )

    # Leakage checks
    group_splits: dict[str, set[str]] = defaultdict(set)
    for a in assignments:
        group_splits[_group_key(next(c for c in eligible if c.crop_id == a.crop_id))].add(a.split)
    for g, splits in group_splits.items():
        if len(splits) > 1:
            raise RuntimeError(f"group leakage detected for {g}: {splits}")

    # Hash family leakage
    sha_splits: dict[str, set[str]] = defaultdict(set)
    crop_by_id = {c.crop_id: c for c in eligible}
    for a in assignments:
        sha_splits[crop_by_id[a.crop_id].sha256].add(a.split)
    for sha, splits in sha_splits.items():
        if len(splits) > 1:
            raise RuntimeError(f"hash leakage for sha {sha[:12]}…: {splits}")

    assignments.sort(key=lambda a: (a.split, a.crop_id))
    canonical = json.dumps(
        [a.model_dump(mode="json") for a in assignments],
        sort_keys=True,
        separators=(",", ":"),
    )
    content_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return SplitManifest(
        split_algorithm_version=SPLIT_ALGORITHM_VERSION,
        seed=seed,
        created_at=_now(),
        assignments=assignments,
        content_sha256=content_sha,
    )


def write_duplicates_and_update_crops(
    private_root: Path,
) -> tuple[list[DuplicateFamilyRecord], list[str]]:
    crops_path = manifest_path(private_root, "crop-manifest.jsonl")
    crops = read_jsonl(crops_path, CropRecord)
    families, warnings = build_duplicate_families(crops)
    write_jsonl_atomic(manifest_path(private_root, "duplicate-families.jsonl"), families)
    write_jsonl_atomic(crops_path, crops)
    return families, warnings


def run_split(private_root: Path, *, seed: int) -> SplitManifest:
    crops = read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
    # Ensure family ids present
    if any(c.duplicate_family_id is None for c in crops):
        families, _ = build_duplicate_families(crops)
        write_jsonl_atomic(manifest_path(private_root, "duplicate-families.jsonl"), families)
        write_jsonl_atomic(manifest_path(private_root, "crop-manifest.jsonl"), crops)
    resolved = read_jsonl(manifest_path(private_root, "resolved-labels.jsonl"), ResolvedLabelRecord)
    manifest = group_aware_split(crops=crops, resolved=resolved, seed=seed)
    write_jsonl_atomic(
        manifest_path(private_root, "split-manifest.jsonl"),
        [manifest],
    )
    return manifest


def freeze_heldout(
    private_root: Path,
    *,
    crop_ids: set[str],
    require_double_review: bool = True,
) -> SplitManifest:
    """Explicit held-out freeze — never auto-run on private data in Task 3A."""

    crops = {
        c.crop_id: c
        for c in read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
    }
    resolved = {
        r.crop_id: r
        for r in read_jsonl(
            manifest_path(private_root, "resolved-labels.jsonl"), ResolvedLabelRecord
        )
    }
    existing_path = manifest_path(private_root, "split-manifest.jsonl")
    existing_list = read_jsonl(existing_path, SplitManifest)
    if not existing_list:
        raise ValueError("Run phase5:dataset:split before freeze-heldout")
    manifest = existing_list[-1]
    assignments = list(manifest.assignments)
    by_crop = {a.crop_id: a for a in assignments}

    for cid in sorted(crop_ids):
        if cid not in crops:
            raise ValueError(f"unknown crop_id: {cid}")
        res = resolved.get(cid)
        if res is None:
            raise ValueError(f"missing resolved label for {cid}")
        if require_double_review and res.status not in {"agreed", "adjudicated"}:
            raise ValueError(
                f"held-out requires agreed/adjudicated review for {cid} (got {res.status})"
            )
        by_crop[cid] = SplitAssignment(
            crop_id=cid,
            split="held_out",
            source_group_id=crops[cid].source_group_id,
            duplicate_family_id=crops[cid].duplicate_family_id,
        )

    new_assignments = sorted(by_crop.values(), key=lambda a: (a.split, a.crop_id))
    canonical = json.dumps(
        [a.model_dump(mode="json") for a in new_assignments],
        sort_keys=True,
        separators=(",", ":"),
    )
    updated = SplitManifest(
        split_algorithm_version=SPLIT_ALGORITHM_VERSION,
        seed=manifest.seed,
        created_at=_now(),
        assignments=new_assignments,
        content_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )
    write_jsonl_atomic(existing_path, [updated])
    return updated

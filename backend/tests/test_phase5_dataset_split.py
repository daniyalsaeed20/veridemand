"""Phase 5 duplicate families and group-aware split tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.app.datasets.phase5.export import import_manual_regions, init_private_dataset
from backend.app.datasets.phase5.ids import new_review_id
from backend.app.datasets.phase5.jsonl_io import append_jsonl, read_jsonl
from backend.app.datasets.phase5.paths import manifest_path
from backend.app.datasets.phase5.resolve import resolve_dataset
from backend.app.datasets.phase5.schemas import CropRecord, ResolvedLabelRecord, ReviewEvent
from backend.app.datasets.phase5.split import (
    build_duplicate_families,
    freeze_heldout,
    group_aware_split,
    run_split,
    write_duplicates_and_update_crops,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "phase5_dataset"


def _label_all_three_classes(root: Path, crops: list[CropRecord]) -> None:
    """Double-label enough crops across three groups for a valid split."""

    # Ensure distinct source groups by rewriting first three crops' groups.
    updated: list[CropRecord] = []
    for i, crop in enumerate(crops):
        sg = f"srcgrp_splitgroup{i:04d}"
        updated.append(crop.model_copy(update={"source_group_id": sg}))
    from backend.app.datasets.phase5.jsonl_io import write_jsonl_atomic

    write_jsonl_atomic(manifest_path(root, "crop-manifest.jsonl"), updated)

    # Need at least one of each class across groups.
    labels = ["printed", "handwritten", "non_text", "printed", "handwritten"]
    events: list[ReviewEvent] = []
    for crop, label in zip(updated, labels, strict=False):
        for role in ("primary", "secondary"):
            events.append(
                ReviewEvent(
                    review_id=new_review_id(),
                    crop_id=crop.crop_id,
                    crop_sha256=crop.sha256,
                    reviewer_id=f"rev_{role}",
                    role=role,
                    action="label",
                    label=label,
                    created_at=datetime.now(UTC),
                )
            )
    append_jsonl(manifest_path(root, "review-events.jsonl"), events)
    resolve_dataset(root)


def test_exact_duplicate_family(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    init_private_dataset(root)
    # Import same region twice from identical pages → identical crop bytes when geometry matches.
    a = import_manual_regions(
        private_root=root,
        regions_jsonl=FIXTURES / "regions" / "manual_regions.jsonl",
        page_image_path=FIXTURES / "pages" / "synthetic_page.png",
        source_group_id="srcgrp_dupaaaa000001",
        page_id="page_dupaaaa00000001",
    )
    b = import_manual_regions(
        private_root=root,
        regions_jsonl=FIXTURES / "regions" / "manual_regions.jsonl",
        page_image_path=FIXTURES / "pages" / "synthetic_page_dup.png",
        source_group_id="srcgrp_dupbbbb000001",
        page_id="page_dupbbbb00000001",
    )
    crops = read_jsonl(manifest_path(root, "crop-manifest.jsonl"), CropRecord)
    families, _warnings = build_duplicate_families(list(crops))
    # At least one family should have >1 member (exact hash match across imports).
    multi = [f for f in families if len(f.crop_ids) > 1]
    assert multi, "expected exact SHA-256 duplicate family"
    assert len(a) >= 1 and len(b) >= 1


def test_group_aware_split_deterministic_and_no_leakage(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    init_private_dataset(root)
    crops = import_manual_regions(
        private_root=root,
        regions_jsonl=FIXTURES / "regions" / "manual_regions.jsonl",
        page_image_path=FIXTURES / "pages" / "synthetic_page.png",
        source_group_id="srcgrp_willrewrite000",
    )
    _label_all_three_classes(root, crops)
    write_duplicates_and_update_crops(root)
    m1 = run_split(root, seed=7)
    m2 = run_split(root, seed=7)
    assert m1.content_sha256 == m2.content_sha256
    assert m1.assignments == m2.assignments

    # No source_group appears in multiple splits
    from collections import defaultdict

    crops2 = {
        c.crop_id: c for c in read_jsonl(manifest_path(root, "crop-manifest.jsonl"), CropRecord)
    }
    group_splits: dict[str, set[str]] = defaultdict(set)
    for a in m1.assignments:
        group_splits[crops2[a.crop_id].source_group_id].add(a.split)
    assert all(len(v) == 1 for v in group_splits.values())


def test_split_fails_without_class_support() -> None:
    crops = [
        CropRecord.model_validate(
            {
                "crop_id": "crop_abcdefghijklmnop",
                "source_group_id": "srcgrp_abcdefghijklmn",
                "document_id": "doc_abcdefghijklmnop",
                "page_id": "page_abcdefghijklmnop",
                "page_index": 0,
                "candidate_source": "manual_region",
                "source_bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                "crop_bbox": {"x": 0.08, "y": 0.08, "width": 0.24, "height": 0.24},
                "applied_padding": {
                    "policy_version": "phase5-crop-pad-v1",
                    "pad_ratio": 0.08,
                    "pad_x": 0.016,
                    "pad_y": 0.016,
                    "clamped": False,
                },
                "crop_relpath": "crops/x.png",
                "sha256": "a" * 64,
                "perceptual_hash": "b" * 16,
                "width_px": 10,
                "height_px": 10,
                "duplicate_family_id": "dupfam_abcdefghijklmn",
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
    ]
    resolved = [
        ResolvedLabelRecord(
            crop_id=crops[0].crop_id,
            crop_sha256=crops[0].sha256,
            status="agreed",
            label="printed",
            training_eligible=True,
            source_group_id=crops[0].source_group_id,
            duplicate_family_id=crops[0].duplicate_family_id,
            resolved_at=datetime.now(UTC),
        )
    ]
    with pytest.raises(ValueError, match="class-support"):
        group_aware_split(crops=crops, resolved=resolved, seed=1)


def test_freeze_heldout_requires_double_review(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    init_private_dataset(root)
    crops = import_manual_regions(
        private_root=root,
        regions_jsonl=FIXTURES / "regions" / "manual_regions.jsonl",
        page_image_path=FIXTURES / "pages" / "synthetic_page.png",
    )
    _label_all_three_classes(root, crops)
    write_duplicates_and_update_crops(root)
    run_split(root, seed=3)
    updated_crops = read_jsonl(manifest_path(root, "crop-manifest.jsonl"), CropRecord)
    target = updated_crops[0].crop_id
    manifest = freeze_heldout(root, crop_ids={target})
    assert any(a.crop_id == target and a.split == "held_out" for a in manifest.assignments)


def test_report_status_line(tmp_path: Path) -> None:
    from backend.app.datasets.phase5.report import build_readiness

    root = tmp_path / "phase5"
    init_private_dataset(root)
    report = build_readiness(root)
    assert report["status_line"] == "DATASET TOOLING READY — HUMAN LABELLING REQUIRED"
    assert report["crop_count"] == 0

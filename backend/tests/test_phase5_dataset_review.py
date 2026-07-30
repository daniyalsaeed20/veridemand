"""Phase 5 review resolve + labeler path-safety tests."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.app.datasets.phase5.export import import_manual_regions, init_private_dataset
from backend.app.datasets.phase5.ids import new_review_id
from backend.app.datasets.phase5.jsonl_io import append_jsonl
from backend.app.datasets.phase5.paths import manifest_path
from backend.app.datasets.phase5.resolve import resolve_dataset, resolve_events_for_crop
from backend.app.datasets.phase5.schemas import CropRecord, ReviewEvent

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "phase5_dataset"


def _seed_crops(root: Path) -> list[CropRecord]:
    init_private_dataset(root)
    return import_manual_regions(
        private_root=root,
        regions_jsonl=FIXTURES / "regions" / "manual_regions.jsonl",
        page_image_path=FIXTURES / "pages" / "synthetic_page.png",
        source_group_id="srcgrp_review0000001",
    )


def _label(crop: CropRecord, *, role: str, label: str, sha: str | None = None) -> ReviewEvent:
    return ReviewEvent(
        review_id=new_review_id(),
        crop_id=crop.crop_id,
        crop_sha256=sha or crop.sha256,
        reviewer_id=f"rev_{role}",
        role=role,
        action="label",
        label=label,
        created_at=datetime.now(UTC),
    )


def test_agree_conflict_adjudicate_uncertain(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    crops = _seed_crops(root)
    a, b, c = crops[0], crops[1], crops[2]
    events = [
        _label(a, role="primary", label="printed"),
        _label(a, role="secondary", label="printed"),
        _label(b, role="primary", label="handwritten"),
        _label(b, role="secondary", label="printed"),
        _label(b, role="adjudicator", label="handwritten"),
        _label(c, role="primary", label="uncertain"),
        _label(c, role="secondary", label="uncertain"),
    ]
    append_jsonl(manifest_path(root, "review-events.jsonl"), events)
    resolved = resolve_dataset(root)
    by_id = {r.crop_id: r for r in resolved}
    assert by_id[a.crop_id].status == "agreed"
    assert by_id[a.crop_id].training_eligible is True
    assert by_id[b.crop_id].status == "adjudicated"
    assert by_id[b.crop_id].label == "handwritten"
    assert by_id[b.crop_id].training_eligible is True
    assert by_id[c.crop_id].status == "agreed"
    assert by_id[c.crop_id].label == "uncertain"
    assert by_id[c.crop_id].training_eligible is False


def test_hash_mismatch_invalidates(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    crops = _seed_crops(root)
    crop = crops[0]
    bad = _label(crop, role="primary", label="printed", sha="0" * 64)
    rec = resolve_events_for_crop(crop, [bad], set())
    assert rec.status == "invalidated_hash_mismatch"
    assert rec.training_eligible is False


def test_conflict_not_training_eligible() -> None:
    crop = CropRecord.model_validate(
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
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    events = [
        _label(crop, role="primary", label="printed"),
        _label(crop, role="secondary", label="handwritten"),
    ]
    rec = resolve_events_for_crop(crop, events, set())
    assert rec.status == "conflict"
    assert rec.training_eligible is False


def test_labeler_rejects_path_traversal(tmp_path: Path) -> None:
    path = Path(__file__).resolve().parents[2] / "scripts" / "phase5" / "labeler_server.py"
    spec = importlib.util.spec_from_file_location("phase5_labeler", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    root = tmp_path / "phase5"
    crops = _seed_crops(root)
    crop = crops[0].model_copy(update={"crop_relpath": "../secret.png"})
    with pytest.raises(ValueError, match="traversal"):
        mod._safe_crop_path(root, crop)

"""Phase 5 Task C1 — coverage sensitivity + server bootstrap isolation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from backend.app.contracts.geometry import NormalisedBoundingBox
from backend.app.datasets.phase5.detector_calibration import (
    summarise_seed_coverage_sensitivity,
)
from backend.app.datasets.phase5.detector_first import classify_seed_coverage
from backend.app.datasets.phase5.schemas import HandwritingSeedRecord

ROOT = Path(__file__).resolve().parents[2]


def _seed(*, page: str, bbox: NormalisedBoundingBox) -> HandwritingSeedRecord:
    sha = "a" * 64
    return HandwritingSeedRecord(
        seed_region_id="seedreg01",
        opaque_document_id="docopaque",
        opaque_page_reference=page,
        source_group_id="srcgroup1",
        reviewer_id="handwriting_reviewer_fixture",
        geometry_normalized=bbox,
        page_render_sha256=sha,
        crop_sha256=sha,
        perceptual_hash="0123456789abcdef",
        source_reference="fixture",
        crop_id="cropid01",
        categories=["cursive"],
        status="active",
        created_at=datetime.now(UTC),
    )


def test_coverage_sensitivity_modes_and_unrelated_reject() -> None:
    seed_bbox = NormalisedBoundingBox(x=0.1, y=0.1, width=0.1, height=0.05)
    exact = NormalisedBoundingBox(x=0.1, y=0.1, width=0.1, height=0.05)
    contained = NormalisedBoundingBox(x=0.05, y=0.05, width=0.3, height=0.2)
    neighbour = NormalisedBoundingBox(x=0.6, y=0.6, width=0.1, height=0.05)
    assert classify_seed_coverage(seed_bbox, [exact]) in {"exact", "near_exact"}
    assert classify_seed_coverage(seed_bbox, [contained]) == "contained"
    assert classify_seed_coverage(seed_bbox, [neighbour]) == "missed"

    seeds = [_seed(page="page_aaaaaaaa", bbox=seed_bbox)]
    report = summarise_seed_coverage_sensitivity(
        seeds,
        {"page_aaaaaaaa": [contained]},
    )
    assert report["sensitivity"]["strict"]["recall"] == 0.0
    assert report["sensitivity"]["containment_friendly"]["recall"] == 1.0
    assert report["sensitivity"]["fragment_union"]["recall"] == 1.0


def test_bootstrap_server_script_is_explicit_and_gitignored_root() -> None:
    text = (ROOT / "scripts/phase5/bootstrap_server_det.py").read_text(encoding="utf-8")
    assert "PP-OCRv5_server_det" in text
    assert "live_detector_replaced" in text
    assert "shadow_server_detector" in text
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".models/" in gitignore


def test_calibrate_script_not_on_live_path() -> None:
    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    worker = (ROOT / "backend/app/extraction/visual/worker.py").read_text(encoding="utf-8")
    assert "calibrate_detector_recall" not in main
    assert "calibrate_detector_recall" not in worker
    assert "load_shadow_detector" not in worker
    assert "bootstrap_server_det" not in worker

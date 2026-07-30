"""Phase 5 crop export / import / verify tests (synthetic fixtures)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.datasets.phase5.export import (
    export_from_phase4_json,
    import_manual_regions,
    init_private_dataset,
    verify_crops,
)
from backend.app.datasets.phase5.jsonl_io import read_jsonl
from backend.app.datasets.phase5.paths import manifest_path
from backend.app.datasets.phase5.schemas import CropRecord

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "phase5_dataset"


def test_init_and_manual_import(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    init_private_dataset(root)
    created = import_manual_regions(
        private_root=root,
        regions_jsonl=FIXTURES / "regions" / "manual_regions.jsonl",
        page_image_path=FIXTURES / "pages" / "synthetic_page.png",
        source_group_id="srcgrp_testgroup0001",
        document_id="doc_testdocument0001",
        page_id="page_testpage0000001",
    )
    assert len(created) >= 4
    problems = verify_crops(root)
    assert problems == []
    crops = read_jsonl(manifest_path(root, "crop-manifest.jsonl"), CropRecord)
    assert all(c.sha256 for c in crops)
    assert all(c.perceptual_hash for c in crops)
    # No text fields on records
    for c in crops:
        dumped = c.model_dump()
        assert "text" not in dumped
        assert "ocr_text" not in dumped


def test_export_from_phase4_json(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    init_private_dataset(root)
    created = export_from_phase4_json(
        private_root=root,
        page_result_path=FIXTURES / "phase4_page_result.json",
        page_image_path=FIXTURES / "pages" / "synthetic_page.png",
        source_group_id="srcgrp_phase4export01",
    )
    assert len(created) >= 1
    assert created[0].candidate_source == "visual_detection"
    assert verify_crops(root) == []


def test_manual_import_rejects_text_field(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    init_private_dataset(root)
    with pytest.raises(ValueError, match="forbidden field"):
        import_manual_regions(
            private_root=root,
            regions_jsonl=FIXTURES / "regions" / "forbidden_text.jsonl",
            page_image_path=FIXTURES / "pages" / "synthetic_page.png",
        )


def test_invalid_geometry_rejected(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    init_private_dataset(root)
    with pytest.raises(ValidationError):
        import_manual_regions(
            private_root=root,
            regions_jsonl=FIXTURES / "regions" / "invalid_geometry.jsonl",
            page_image_path=FIXTURES / "pages" / "synthetic_page.png",
        )


def test_export_resume_skips_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    init_private_dataset(root)
    kwargs = dict(
        private_root=root,
        page_result_path=FIXTURES / "phase4_page_result.json",
        page_image_path=FIXTURES / "pages" / "synthetic_page.png",
        source_group_id="srcgrp_resume0000001",
        document_id="doc_resume0000000001",
        page_id="page_resume0000000001",
    )
    first = export_from_phase4_json(**kwargs)  # type: ignore[arg-type]
    second = export_from_phase4_json(**kwargs)  # type: ignore[arg-type]
    assert len(first) >= 1
    assert second == []

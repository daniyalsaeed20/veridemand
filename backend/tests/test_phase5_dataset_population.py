"""Phase 5 Task 3B register / queue / backup / strip tests (synthetic only)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from backend.app.datasets.phase5.backup import backup_manifests
from backend.app.datasets.phase5.export import import_manual_regions, init_private_dataset
from backend.app.datasets.phase5.geometry_strip import strip_text_fields
from backend.app.datasets.phase5.ids import new_review_id
from backend.app.datasets.phase5.jsonl_io import append_jsonl, read_jsonl
from backend.app.datasets.phase5.paths import manifest_path
from backend.app.datasets.phase5.queue import build_primary_review_queue
from backend.app.datasets.phase5.register import infer_source_family, register_from_batch_manifest
from backend.app.datasets.phase5.report import build_readiness, render_committed_aggregate_markdown
from backend.app.datasets.phase5.schemas import DocumentRecord, ReviewEvent
from backend.app.datasets.phase5.split import write_duplicates_and_update_crops

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "phase5_dataset"


def test_infer_source_family_from_opaque_label() -> None:
    assert infer_source_family("private_police_scan") == "police_form"
    assert infer_source_family("private_billing_digital") == "billing_ledger"
    assert infer_source_family("private_medical_embedded_ocr") == "medical_form"
    assert infer_source_family("private_mixed_001") == "other"


def test_strip_text_fields_removes_transcripts() -> None:
    payload = {
        "lines": [{"bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1}, "text": "SECRET"}],
        "source_label": "leak",
    }
    cleaned = strip_text_fields(payload)
    assert "text" not in cleaned["lines"][0]
    assert "source_label" not in cleaned
    assert cleaned["lines"][0]["bbox"]["x"] == 0.1


def test_register_from_batch_reuses_sha(tmp_path: Path) -> None:
    fixtures = tmp_path / "private"
    fixtures.mkdir()
    # Minimal PDF via pypdf
    from pypdf import PdfWriter

    pdf = fixtures / "doc_a.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with pdf.open("wb") as handle:
        writer.write(handle)
    batch = tmp_path / "batch.json"
    batch.write_text(
        json.dumps({"documents": {"private_billing_test": "doc_a.pdf"}}),
        encoding="utf-8",
    )
    root = tmp_path / "phase5"
    init_private_dataset(root)
    docs1, stats1 = register_from_batch_manifest(
        private_root=root, batch_manifest=batch, fixtures_private=fixtures
    )
    docs2, stats2 = register_from_batch_manifest(
        private_root=root, batch_manifest=batch, fixtures_private=fixtures
    )
    assert stats1["registered_new"] == 1
    assert stats2["reused"] == 1
    assert docs1[0].document_id == docs2[0].document_id
    stored = read_jsonl(manifest_path(root, "document-manifest.jsonl"), DocumentRecord)
    assert len(stored) == 1
    assert stored[0].source_family == "billing_ledger"


def test_backup_and_queue_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    init_private_dataset(root)
    crops = import_manual_regions(
        private_root=root,
        regions_jsonl=FIXTURES / "regions" / "manual_regions.jsonl",
        page_image_path=FIXTURES / "pages" / "synthetic_page.png",
        source_group_id="srcgrp_queue00000001",
    )
    assert len(crops) >= 3
    backup = backup_manifests(root)
    assert (backup / "backup-meta.json").is_file()
    write_duplicates_and_update_crops(root)
    q1 = build_primary_review_queue(root, seed=7)
    q2 = build_primary_review_queue(root, seed=7)
    assert q1.content_sha256 == q2.content_sha256
    assert [e.crop_id for e in q1.entries] == [e.crop_id for e in q2.entries]
    assert len(q1.entries) == len(crops)


def test_queue_skips_reviewed_and_exact_dup_noncanonical(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    init_private_dataset(root)
    crops = import_manual_regions(
        private_root=root,
        regions_jsonl=FIXTURES / "regions" / "manual_regions.jsonl",
        page_image_path=FIXTURES / "pages" / "synthetic_page.png",
    )
    write_duplicates_and_update_crops(root)
    # Mark first crop reviewed
    crop = crops[0]
    append_jsonl(
        manifest_path(root, "review-events.jsonl"),
        [
            ReviewEvent(
                review_id=new_review_id(),
                crop_id=crop.crop_id,
                crop_sha256=crop.sha256,
                reviewer_id="rev_human_test",
                role="primary",
                action="label",
                label="printed",
                created_at=datetime.now(UTC),
            )
        ],
    )
    queue = build_primary_review_queue(root, seed=1)
    assert crop.crop_id not in {e.crop_id for e in queue.entries}


def test_report_status_primary_pending_and_redacted(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    init_private_dataset(root)
    report = build_readiness(root)
    assert "COVERAGE AND ANNOTATION PILOT REQUIRED" in report["status_line"]
    assert report["training_authorised"] is False
    md = render_committed_aggregate_markdown(report)
    assert "fixtures/private" not in md
    assert ".pdf" not in md

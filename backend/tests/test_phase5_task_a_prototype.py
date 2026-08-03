"""Phase 5 Task A prototype queue and single-pass review tests (synthetic)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import scripts.phase5.labeler_server as labeler
from PIL import Image, ImageDraw

from backend.app.datasets.phase5.constants import (
    PROTOTYPE_PRIMARY_QUEUE_VERSION,
    PROTOTYPE_PRIMARY_SEED,
)
from backend.app.datasets.phase5.export import init_private_dataset
from backend.app.datasets.phase5.jsonl_io import append_jsonl, read_jsonl, write_jsonl_atomic
from backend.app.datasets.phase5.paths import manifest_path, reports_dir
from backend.app.datasets.phase5.pilot import build_annotation_pilot
from backend.app.datasets.phase5.prototype import (
    build_prototype_label_aggregate,
    build_prototype_primary_queue,
    render_prototype_labels_markdown,
)
from backend.app.datasets.phase5.resolve import resolve_events_for_crop
from backend.app.datasets.phase5.schemas import (
    CropRecord,
    DocumentRecord,
    ReviewEvent,
    SourceRecord,
)
from backend.app.datasets.phase5.split import write_duplicates_and_update_crops

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "phase5_dataset"


def _write_page(root: Path, *, page_id: str, seed: int = 0) -> Path:
    pages = root / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (200, 200), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    for i in range(20):
        x = (seed * 17 + i * 13) % 180
        y = (seed * 29 + i * 11) % 180
        draw.point((x, y), fill=(seed % 200, (i * 9) % 200, (seed + i) % 200))
    draw.rectangle([10, 10, 90, 40], outline=(0, 0, 0))
    png = pages / f"{page_id}.png"
    img.save(png)
    result = {
        "page_number": 1,
        "lines": [
            {
                "id": "line_000000",
                "bbox": {"x": 0.05, "y": 0.05, "width": 0.4, "height": 0.15},
                "polygon": {
                    "points": [
                        {"x": 0.05, "y": 0.05},
                        {"x": 0.45, "y": 0.05},
                        {"x": 0.45, "y": 0.2},
                        {"x": 0.05, "y": 0.2},
                    ]
                },
            }
        ],
        "words": [],
        "blocks": [],
        "repair_regions": [],
    }
    (pages / f"{page_id}.result.json").write_text(json.dumps(result), encoding="utf-8")
    return png


def _seed_dataset(root: Path, *, pages: int = 6, groups: int = 6) -> None:
    init_private_dataset(root)
    now = datetime.now(UTC)
    docs: list[DocumentRecord] = []
    sources: list[SourceRecord] = []
    for g in range(groups):
        doc_id = f"doc_proto{g:011d}"
        group_id = f"srcgrp_proto{g:09d}"
        family = (
            "medical_form",
            "police_form",
            "billing_ledger",
            "fax_record",
            "insurance_letter",
            "image_document",
        )[g % 6]
        docs.append(
            DocumentRecord(
                document_id=doc_id,
                source_group_id=group_id,
                source_family=family,  # type: ignore[arg-type]
                document_sha256=f"{g + 1:064x}",
                page_count=pages,
                opaque_label=f"synth_{g}",
                source_relpath=f"synth_{g}.pdf",
                created_at=now,
            )
        )
        for p in range(pages):
            page_id = f"page_proto{g:04d}{p:08d}"
            _write_page(root, page_id=page_id, seed=g * 100 + p)
            sources.append(
                SourceRecord(
                    source_group_id=group_id,
                    document_id=doc_id,
                    page_id=page_id,
                    page_index=p,
                    page_width_px=200,
                    page_height_px=200,
                    page_relpath=f"pages/{page_id}.png",
                    source_family=family,  # type: ignore[arg-type]
                    document_sha256=f"{g + 1:064x}",
                    page_count=pages,
                    created_at=now,
                )
            )
    write_jsonl_atomic(manifest_path(root, "document-manifest.jsonl"), docs)
    write_jsonl_atomic(manifest_path(root, "source-manifest.jsonl"), sources)

    # Import crops via pilot path: create crop records manually with unique hashes.
    from backend.app.datasets.phase5.export import export_from_phase4_json

    for source in sources:
        page_png = root / "pages" / f"{source.page_id}.png"
        result = root / "pages" / f"{source.page_id}.result.json"
        export_from_phase4_json(
            private_root=root,
            page_result_path=result,
            page_image_path=page_png,
            source_group_id=source.source_group_id,
            document_id=source.document_id,
            page_id=source.page_id,
        )
    write_duplicates_and_update_crops(root)


def test_prototype_queue_requires_explicit_version(tmp_path: Path) -> None:
    _seed_dataset(tmp_path)
    build_annotation_pilot(tmp_path, target_size=24, primary_seed=3101, secondary_seed=3102)
    with pytest.raises(ValueError, match="phase5-prototype-primary-v1"):
        build_prototype_primary_queue(tmp_path, queue_version="wrong-version")


def test_prototype_selection_deterministic_and_excludes_coverage(tmp_path: Path) -> None:
    _seed_dataset(tmp_path, pages=4, groups=6)
    build_annotation_pilot(tmp_path, target_size=24, primary_seed=3101, secondary_seed=3102)
    crops = read_jsonl(manifest_path(tmp_path, "crop-manifest.jsonl"), CropRecord)
    # Mark two pages as coverage-correction.
    bad_pages = sorted({c.page_id for c in crops})[:2]
    reports_dir(tmp_path).mkdir(parents=True, exist_ok=True)
    lines = []
    for page in bad_pages:
        lines.append(
            json.dumps(
                {
                    "worklist_version": "phase5-coverage-worklist-v1",
                    "opaque_page_reference": page,
                    "opaque_document_reference": "doc_opaque_test",
                    "coverage_outcome": "missing_region",
                    "issue_flags": ["missing_region"],
                    "coverage_event_id": f"covevt_{page[-12:]}",
                    "page_render_hash": "a" * 64,
                    "overlay_hash": "b" * 64,
                    "reviewed_at": datetime.now(UTC).isoformat(),
                    "reviewer_id": "cov_reviewer_01",
                }
            )
        )
    (reports_dir(tmp_path) / "coverage-correction-worklist.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    q1 = build_prototype_primary_queue(
        tmp_path,
        queue_version=PROTOTYPE_PRIMARY_QUEUE_VERSION,
        seed=PROTOTYPE_PRIMARY_SEED,
        target_size=12,
    )
    q2 = build_prototype_primary_queue(
        tmp_path,
        queue_version=PROTOTYPE_PRIMARY_QUEUE_VERSION,
        seed=PROTOTYPE_PRIMARY_SEED,
        target_size=12,
    )
    assert q1.content_sha256 == q2.content_sha256
    assert len(q1.entries) == len(q2.entries)
    assert [e.crop_id for e in q1.entries] == [e.crop_id for e in q2.entries]
    assert q1.excluded_active_coverage_page_count == 2
    assert q1.queue_name == "prototype-primary"
    assert q1.authorised_for_review is True
    assert q1.source_group_count == 6

    crop_by_id = {c.crop_id: c for c in crops}
    for entry in q1.entries:
        assert crop_by_id[entry.crop_id].page_id not in set(bad_pages)
        assert entry.crop_sha256 == crop_by_id[entry.crop_id].sha256

    # Exact duplicates excluded (unique SHA in queue).
    shas = [e.crop_sha256 for e in q1.entries]
    assert len(shas) == len(set(shas))

    # Corpus crops not deleted.
    assert len(crops) == len(read_jsonl(manifest_path(tmp_path, "crop-manifest.jsonl"), CropRecord))


def test_prototype_fallback_when_fewer_than_target(tmp_path: Path) -> None:
    _seed_dataset(tmp_path, pages=2, groups=3)
    build_annotation_pilot(tmp_path, target_size=6, primary_seed=3101, secondary_seed=3102)
    q = build_prototype_primary_queue(
        tmp_path,
        queue_version=PROTOTYPE_PRIMARY_QUEUE_VERSION,
        seed=4101,
        target_size=300,
    )
    assert len(q.entries) < 300
    assert len(q.entries) > 0


def test_single_review_prototype_eligible_uncertain_not(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    crop = CropRecord(
        crop_id="crop_abcd12345678",
        source_group_id="srcgrp_abcd1234",
        document_id="doc_abcd12345678",
        page_id="page_abcd12345678",
        page_index=0,
        candidate_source="full_page_ocr",
        source_bbox={"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1},
        crop_bbox={"x": 0.08, "y": 0.08, "width": 0.24, "height": 0.14},
        applied_padding={
            "policy_version": "phase5-crop-pad-v1",
            "pad_ratio": 0.08,
            "pad_x": 0.02,
            "pad_y": 0.02,
            "clamped": False,
        },
        crop_relpath="crops/crop_abcd12345678.png",
        sha256="c" * 64,
        perceptual_hash="0123456789abcdef",
        width_px=40,
        height_px=20,
        created_at=now,
    )
    printed_ev = ReviewEvent(
        review_id="review_abcd12345678",
        crop_id=crop.crop_id,
        crop_sha256=crop.sha256,
        reviewer_id="proto_reviewer_01",
        role="primary",
        action="label",
        label="printed",
        queue_name="prototype-primary",
        created_at=now,
    )
    res = resolve_events_for_crop(crop, [printed_ev], set())
    assert res.status == "single_review"
    assert res.training_eligible is False
    assert res.prototype_model_eligible is True

    uncertain_ev = ReviewEvent(
        review_id="review_efgh12345678",
        crop_id=crop.crop_id,
        crop_sha256=crop.sha256,
        reviewer_id="proto_reviewer_01",
        role="primary",
        action="label",
        label="uncertain",
        queue_name="prototype-primary",
        created_at=now,
    )
    res_u = resolve_events_for_crop(crop, [uncertain_ev], set())
    assert res_u.prototype_model_eligible is False
    assert res_u.training_eligible is False

    exclude_ev = ReviewEvent(
        review_id="review_ijkl12345678",
        crop_id=crop.crop_id,
        crop_sha256=crop.sha256,
        reviewer_id="proto_reviewer_01",
        role="primary",
        action="exclude",
        label=None,
        queue_name="prototype-primary",
        created_at=now,
    )
    res_x = resolve_events_for_crop(crop, [exclude_ev], set())
    assert res_x.status == "excluded"
    assert res_x.prototype_model_eligible is False


def test_labeler_requires_explicit_prototype_queue_and_rejects_full_default(
    tmp_path: Path,
) -> None:
    _seed_dataset(tmp_path, pages=2, groups=3)
    build_annotation_pilot(tmp_path, target_size=6, primary_seed=3101, secondary_seed=3102)
    build_prototype_primary_queue(
        tmp_path, queue_version=PROTOTYPE_PRIMARY_QUEUE_VERSION, seed=4101, target_size=4
    )
    # Missing --queue fails argparse.
    with pytest.raises(SystemExit):
        labeler.main(["--root", str(tmp_path), "--reviewer", "proto_reviewer_01"])
    # Full primary without authorise fails.
    code = labeler.main(
        ["--root", str(tmp_path), "--queue", "full-primary", "--reviewer", "rev_test01"]
    )
    assert code == 2
    # Bad reviewer for prototype.
    code = labeler.main(
        ["--root", str(tmp_path), "--queue", "prototype-primary", "--reviewer", "alice"]
    )
    assert code == 2
    # proto_reviewer accepted at CLI validation (server start would block; use dry parse path).
    assert labeler._reviewer_id_ok("prototype-primary", "proto_reviewer_01")
    assert not labeler._reviewer_id_ok("pilot-primary", "proto_reviewer_01")


def test_prototype_aggregate_privacy(tmp_path: Path) -> None:
    _seed_dataset(tmp_path, pages=2, groups=3)
    build_annotation_pilot(tmp_path, target_size=6, primary_seed=3101, secondary_seed=3102)
    queue = build_prototype_primary_queue(
        tmp_path, queue_version=PROTOTYPE_PRIMARY_QUEUE_VERSION, seed=4101, target_size=4
    )
    now = datetime.now(UTC)
    crops = {
        c.crop_id: c for c in read_jsonl(manifest_path(tmp_path, "crop-manifest.jsonl"), CropRecord)
    }
    events: list[ReviewEvent] = []
    # Ensure all three model classes plus uncertain appear regardless of queue size.
    forced = ["printed", "handwritten", "non_text", "uncertain"]
    for i, entry in enumerate(queue.entries):
        crop = crops[entry.crop_id]
        label = forced[i] if i < len(forced) else "printed"
        events.append(
            ReviewEvent(
                review_id=f"review_proto{i:010d}",
                crop_id=entry.crop_id,
                crop_sha256=crop.sha256,
                reviewer_id="proto_reviewer_01",
                role="primary",
                action="label",
                label=label,  # type: ignore[arg-type]
                queue_name="prototype-primary",
                created_at=now,
            )
        )
    # If queue shorter than 3, still inject isn't possible — require size.
    assert len(queue.entries) >= 3
    append_jsonl(manifest_path(tmp_path, "review-events.jsonl"), events)
    report = build_prototype_label_aggregate(tmp_path)
    md = render_prototype_labels_markdown(report)
    assert "proto_reviewer_01" not in md
    for entry in queue.entries:
        assert entry.crop_id not in md
    assert "fixtures/private" not in md
    assert "synth_" not in md
    assert report["printed"] >= 1
    assert report["handwritten"] >= 1
    assert report["non_text"] >= 1
    assert report["prototype_model_eligible_count"] >= 3
    assert "PROTOTYPE LABEL SAMPLE READY" in report["readiness"]

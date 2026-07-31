"""Phase 5 Task 3C pilot, coverage, provenance, and isolation tests (synthetic)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw

from backend.app.datasets.phase5.block_coverage import audit_block_coverage
from backend.app.datasets.phase5.coverage import build_coverage_review, build_page_overlay
from backend.app.datasets.phase5.export import import_manual_regions, init_private_dataset
from backend.app.datasets.phase5.jsonl_io import append_jsonl, read_jsonl, write_jsonl_atomic
from backend.app.datasets.phase5.paths import manifest_path
from backend.app.datasets.phase5.pilot import build_adjudication_queue, build_annotation_pilot
from backend.app.datasets.phase5.pilot_report import build_pilot_agreement_report, cohens_kappa
from backend.app.datasets.phase5.provenance_audit import audit_candidate_provenance
from backend.app.datasets.phase5.report import build_readiness, render_committed_aggregate_markdown
from backend.app.datasets.phase5.schemas import (
    CropRecord,
    DocumentRecord,
    ReviewEvent,
    ReviewQueueManifest,
    SourceRecord,
)
from backend.app.datasets.phase5.source_manifest_dedupe import dedupe_source_manifest
from backend.app.datasets.phase5.split import write_duplicates_and_update_crops

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "phase5_dataset"


def _write_page_with_blocks(
    root: Path, *, page_id: str, seed: int = 0, with_gap: bool = False
) -> Path:
    pages = root / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    # Unique background noise so crops are not exact-SHA duplicates across pages.
    img = Image.new("RGB", (200, 200), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    for i in range(20):
        x = (seed * 17 + i * 13) % 180
        y = (seed * 29 + i * 11) % 180
        draw.point((x, y), fill=(seed % 200, (i * 9) % 200, (seed + i) % 200))
    draw.rectangle([10, 10, 90, 40], outline=(0, 0, 0))
    png = pages / f"{page_id}.png"
    img.save(png)
    lines = [
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
    ]
    blocks = [
        {
            "id": "block_000000",
            "bbox": lines[0]["bbox"],
            "polygon": lines[0]["polygon"],
            "line_ids": ["line_000000"],
        }
    ]
    if with_gap:
        blocks.append(
            {
                "id": "block_000001",
                "bbox": {"x": 0.6, "y": 0.6, "width": 0.3, "height": 0.3},
                "polygon": {
                    "points": [
                        {"x": 0.6, "y": 0.6},
                        {"x": 0.9, "y": 0.6},
                        {"x": 0.9, "y": 0.9},
                        {"x": 0.6, "y": 0.9},
                    ]
                },
                "line_ids": [],
            }
        )
    result = {
        "page_number": 1,
        "lines": lines,
        "words": [],
        "blocks": blocks,
        "repair_regions": [],
    }
    result_path = pages / f"{page_id}.result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    return png


def _seed_multi_page_dataset(root: Path, *, pages: int = 8, groups: int = 3) -> list[CropRecord]:
    init_private_dataset(root)
    now = datetime.now(UTC)
    docs: list[DocumentRecord] = []
    sources: list[SourceRecord] = []
    for g in range(groups):
        doc_id = f"doc_seed{g:012d}"
        group_id = f"srcgrp_seed{g:010d}"
        docs.append(
            DocumentRecord(
                document_id=doc_id,
                source_group_id=group_id,
                source_family="other",
                document_sha256=f"{g + 1:064x}",
                page_count=pages,
                opaque_label=f"synth_{g}",
                source_relpath=f"synth_{g}.pdf",
                created_at=now,
            )
        )
        for p in range(pages):
            page_id = f"page_seed{g:04d}{p:08d}"
            _write_page_with_blocks(
                root, page_id=page_id, seed=g * 100 + p + 1, with_gap=(p == 0 and g == 0)
            )
            sources.append(
                SourceRecord(
                    source_group_id=group_id,
                    document_id=doc_id,
                    page_id=page_id,
                    page_index=p,
                    page_width_px=200,
                    page_height_px=200,
                    page_relpath=f"pages/{page_id}.png",
                    source_family="other",
                    created_at=now,
                )
            )
    write_jsonl_atomic(manifest_path(root, "document-manifest.jsonl"), docs)
    write_jsonl_atomic(manifest_path(root, "source-manifest.jsonl"), sources)

    crops: list[CropRecord] = []
    for g in range(groups):
        for p in range(pages):
            page_id = f"page_seed{g:04d}{p:08d}"
            regions = root / f"regions_{g}_{p}.jsonl"
            # Distinct bboxes so padded crops differ even on similar backgrounds.
            region_specs = []
            for i in range(3):
                x = 0.05 + 0.25 * i
                y = 0.1 + 0.15 * ((g + p + i) % 3)
                region_specs.append(
                    {
                        "bbox": {
                            "x": round(x, 4),
                            "y": round(y, 4),
                            "width": 0.18,
                            "height": 0.12,
                        }
                    }
                )
                # Paint unique marker inside the region so SHA differs.
                img_path = root / "pages" / f"{page_id}.png"
                with Image.open(img_path) as im:
                    canvas = im.copy()
                    d = ImageDraw.Draw(canvas)
                    px = int(x * 200) + 2
                    py = int(y * 200) + 2
                    d.rectangle(
                        [px, py, px + 8 + i, py + 8 + g],
                        fill=((g * 40 + i * 20) % 255, (p * 30) % 255, (i * 50) % 255),
                    )
                    canvas.save(img_path)
            regions.write_text(
                "\n".join(json.dumps(spec) for spec in region_specs) + "\n",
                encoding="utf-8",
            )
            created = import_manual_regions(
                private_root=root,
                regions_jsonl=regions,
                page_image_path=root / "pages" / f"{page_id}.png",
                source_group_id=f"srcgrp_seed{g:010d}",
                document_id=f"doc_seed{g:012d}",
                page_id=page_id,
                page_index=p,
            )
            crops.extend(created)
    write_duplicates_and_update_crops(root)
    return crops


def test_source_manifest_dedupe(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    init_private_dataset(root)
    now = datetime.now(UTC)
    rows = [
        SourceRecord(
            source_group_id="srcgrp_aaaaaaaaaaaa",
            document_id="doc_aaaaaaaaaaaaaaaa",
            page_id="page_aaaaaaaaaaaaaaaa",
            page_index=0,
            created_at=now,
        ),
        SourceRecord(
            source_group_id="srcgrp_aaaaaaaaaaaa",
            document_id="doc_aaaaaaaaaaaaaaaa",
            page_id="page_aaaaaaaaaaaaaaaa",
            page_index=0,
            created_at=now,
        ),
        SourceRecord(
            source_group_id="srcgrp_bbbbbbbbbbbb",
            document_id="doc_bbbbbbbbbbbbbbbb",
            page_id="page_bbbbbbbbbbbbbbbb",
            page_index=1,
            created_at=now,
        ),
    ]
    write_jsonl_atomic(manifest_path(root, "source-manifest.jsonl"), rows)
    meta = dedupe_source_manifest(root, backup=True)
    assert meta["rows_before"] == 3
    assert meta["rows_after"] == 2
    assert meta["duplicate_rows_removed"] == 1
    kept = read_jsonl(manifest_path(root, "source-manifest.jsonl"), SourceRecord)
    assert len(kept) == 2
    assert len({s.page_id for s in kept}) == 2


def test_provenance_preserves_full_page_ocr(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    _seed_multi_page_dataset(root, pages=2, groups=1)
    report = audit_candidate_provenance(root)
    assert report["verdict"] == "correct"
    by_name = {c["candidate_source"]: c for c in report["categories"]}
    assert by_name["manual_region"]["candidate_record_count"] > 0
    assert by_name["targeted_repair"]["candidate_record_count"] == 0


def test_block_coverage_gap_and_full_proxy(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    init_private_dataset(root)
    page_id = "page_blockcov0000001"
    _write_page_with_blocks(root, page_id=page_id, seed=99, with_gap=True)
    now = datetime.now(UTC)
    append_jsonl(
        manifest_path(root, "source-manifest.jsonl"),
        [
            SourceRecord(
                source_group_id="srcgrp_blockcov00001",
                document_id="doc_blockcov00000001",
                page_id=page_id,
                page_index=0,
                created_at=now,
            )
        ],
    )
    summary = audit_block_coverage(root)
    assert summary["skipped_block_count"] == 2
    assert summary["blocks_with_coverage_gaps"] >= 1


def test_page_overlay_and_coverage_queue(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    crops = _seed_multi_page_dataset(root, pages=3, groups=2)
    assert crops
    summary = build_coverage_review(root)
    assert summary["page_count"] == 6
    assert summary["overlays_written"] == 6
    assert summary["manual_region_status"] == "not_yet_human_verified"
    assert summary["human_coverage_events"] == 0


def test_pilot_sampling_determinism_and_dual_queues(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    _seed_multi_page_dataset(root, pages=4, groups=3)
    m1 = build_annotation_pilot(root, target_size=20, primary_seed=3101, secondary_seed=3102)
    m2 = build_annotation_pilot(root, target_size=20, primary_seed=3101, secondary_seed=3102)
    assert m1.content_sha256 == m2.content_sha256
    assert m1.crop_count == 20
    assert m1.pages_represented >= 12
    assert m1.source_groups_represented == 3
    primary = read_jsonl(manifest_path(root, "pilot-primary-queue.jsonl"), ReviewQueueManifest)[-1]
    secondary = read_jsonl(manifest_path(root, "pilot-secondary-queue.jsonl"), ReviewQueueManifest)[
        -1
    ]
    assert primary.authorised_for_review is True
    assert secondary.authorised_for_review is True
    p_ids = [e.crop_id for e in primary.entries]
    s_ids = [e.crop_id for e in secondary.entries]
    assert sorted(p_ids) == sorted(s_ids)
    assert p_ids != s_ids
    assert p_ids != list(reversed(s_ids))
    assert primary.seed == 3101
    assert secondary.seed == 3102


def test_per_page_cap_and_exact_dup_removal(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    crops = _seed_multi_page_dataset(root, pages=2, groups=1)
    # Duplicate one crop PNG into another record is handled by duplicates pass already.
    write_duplicates_and_update_crops(root)
    manifest = build_annotation_pilot(
        root, target_size=min(10, len(crops)), primary_seed=1, secondary_seed=2
    )
    assert manifest.per_page_max <= 10
    assert manifest.crop_count == len({e.canonical_crop_id for e in manifest.entries})


def test_adjudication_after_conflict(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    crops = _seed_multi_page_dataset(root, pages=2, groups=1)
    assert crops
    pilot = build_annotation_pilot(root, target_size=4, primary_seed=3101, secondary_seed=3102)
    crop_id = pilot.entries[0].canonical_crop_id
    crop = next(c for c in crops if c.crop_id == crop_id)
    now = datetime.now(UTC)
    append_jsonl(
        manifest_path(root, "review-events.jsonl"),
        [
            ReviewEvent(
                review_id="review_aaaaaaaaaaaaaa",
                crop_id=crop.crop_id,
                crop_sha256=crop.sha256,
                reviewer_id="rev_primary_a",
                role="primary",
                action="label",
                label="printed",
                queue_name="pilot-primary",
                created_at=now,
            ),
            ReviewEvent(
                review_id="review_bbbbbbbbbbbbbb",
                crop_id=crop.crop_id,
                crop_sha256=crop.sha256,
                reviewer_id="rev_secondary_b",
                role="secondary",
                action="label",
                label="handwritten",
                queue_name="pilot-secondary",
                created_at=now,
            ),
        ],
    )
    adj = build_adjudication_queue(root)
    assert adj.authorised_for_review is True
    assert len(adj.entries) == 1
    assert adj.entries[0].crop_id == crop.crop_id
    report = build_pilot_agreement_report(root)
    assert report["conflict_count"] == 1
    assert report["paired_label_count"] == 1


def test_cohens_kappa_known_and_degenerate() -> None:
    assert cohens_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) is not None
    # Perfect single-class agreement → undefined.
    assert cohens_kappa(["a", "a", "a"], ["a", "a", "a"]) is None
    assert cohens_kappa([], []) is None


def test_aggregate_report_privacy(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    _seed_multi_page_dataset(root, pages=2, groups=1)
    build_annotation_pilot(root, target_size=4, primary_seed=3101, secondary_seed=3102)
    report = build_readiness(root)
    md = render_committed_aggregate_markdown(report)
    assert "PRIVATE CORPUS POPULATED" in md
    assert "fixtures/private" not in md
    assert "crop_" not in md or "crop count" in md.lower() or "Pilot crop" in md
    # Opaque crop ids must not appear.
    for entry in read_jsonl(manifest_path(root, "crop-manifest.jsonl"), CropRecord):
        assert entry.crop_id not in md
        assert entry.sha256 not in md


def test_overlay_creation_unit(tmp_path: Path) -> None:
    root = tmp_path / "phase5"
    init_private_dataset(root)
    page_id = "page_overlay00000001"
    png = _write_page_with_blocks(root, page_id=page_id)
    out = tmp_path / "overlay.png"
    build_page_overlay(
        page_image_path=png,
        page_result_path=root / "pages" / f"{page_id}.result.json",
        crops=[],
        out_path=out,
        skipped_block_bboxes=[{"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2}],
    )
    assert out.is_file()
    assert out.with_suffix(".meta.json").is_file()
    meta = json.loads(out.with_suffix(".meta.json").read_text(encoding="utf-8"))
    assert "text" not in meta
    assert meta["opaque_page_reference"] == page_id


def test_labeler_requires_queue_and_rejects_full_without_auth(tmp_path: Path) -> None:
    import scripts.phase5.labeler_server as labeler

    root = tmp_path / "phase5"
    _seed_multi_page_dataset(root, pages=2, groups=1)
    build_annotation_pilot(root, target_size=4, primary_seed=3101, secondary_seed=3102)
    # full queue without auth
    code = labeler.main(
        ["--root", str(root), "--queue", "full-primary", "--reviewer", "rev_tester"]
    )
    assert code == 2
    # unknown reviewer format
    code = labeler.main(["--root", str(root), "--queue", "pilot-primary", "--reviewer", "bad"])
    assert code == 2

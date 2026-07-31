"""Page-level coverage-review artefacts and queue (loopback; no script labels)."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from backend.app.datasets.phase5.block_coverage import audit_block_coverage
from backend.app.datasets.phase5.constants import COVERAGE_QUEUE_VERSION
from backend.app.datasets.phase5.hashes import sha256_file
from backend.app.datasets.phase5.jsonl_io import read_jsonl, write_jsonl_atomic
from backend.app.datasets.phase5.paths import (
    ensure_layout,
    manifest_path,
    pages_dir,
    reports_dir,
)
from backend.app.datasets.phase5.schemas import (
    BlockCoverageRecord,
    CoverageQueueEntry,
    CoverageQueueManifest,
    CropRecord,
    DocumentRecord,
    SourceRecord,
)


def coverage_dir(private_root: Path) -> Path:
    return private_root / "coverage"


def _now() -> datetime:
    return datetime.now(UTC)


def _draw_box(
    draw: ImageDraw.ImageDraw,
    bbox: dict[str, Any],
    *,
    width_px: int,
    height_px: int,
    outline: tuple[int, int, int],
    width: int = 2,
) -> None:
    x0 = round(float(bbox["x"]) * width_px)
    y0 = round(float(bbox["y"]) * height_px)
    x1 = round((float(bbox["x"]) + float(bbox["width"])) * width_px)
    y1 = round((float(bbox["y"]) + float(bbox["height"])) * height_px)
    draw.rectangle([x0, y0, x1, y1], outline=outline, width=width)


def build_page_overlay(
    *,
    page_image_path: Path,
    page_result_path: Path,
    crops: list[CropRecord],
    out_path: Path,
    skipped_block_bboxes: list[dict[str, Any]],
    max_crop_boxes: int = 800,
) -> None:
    """Write overlay PNG: page + crop boxes + skipped-block outlines. No OCR text."""

    with Image.open(page_image_path) as img:
        canvas = img.convert("RGB").copy()
    draw = ImageDraw.Draw(canvas)
    w, h = canvas.size
    # Deterministic thin for dense pages (lexicographic crop_id order).
    drawn = sorted(crops, key=lambda c: c.crop_id)[:max_crop_boxes]
    for crop in drawn:
        _draw_box(
            draw,
            {
                "x": crop.crop_bbox.x,
                "y": crop.crop_bbox.y,
                "width": crop.crop_bbox.width,
                "height": crop.crop_bbox.height,
            },
            width_px=w,
            height_px=h,
            outline=(0, 140, 255),
            width=2,
        )
    for bbox in skipped_block_bboxes:
        _draw_box(draw, bbox, width_px=w, height_px=h, outline=(220, 80, 0), width=1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="PNG", optimize=True)
    # Side-car stats (opaque refs only).
    meta = {
        "opaque_page_reference": page_result_path.name.replace(".result.json", ""),
        "exported_crop_count": len(crops),
        "overlay_boxes_drawn": len(drawn),
        "skipped_block_outline_count": len(skipped_block_bboxes),
        "overlay_relpath": out_path.name,
        "note": "Coverage artefact only; not a script label.",
    }
    out_path.with_suffix(".meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )


def _priority_for_page(
    *,
    source: SourceRecord | None,
    document: DocumentRecord | None,
    crop_count: int,
    gap_count: int,
    median_crops: float,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    family = (
        source.source_family
        if source and source.source_family
        else (document.source_family if document else None)
    )
    if family == "police_form":
        score += 100
        reasons.append("police_form")
    if family == "medical_form":
        score += 80
        reasons.append("medical_form")
    if family == "image_document":
        score += 60
        reasons.append("image_document")
    if gap_count > 0:
        score += 50 + min(gap_count, 20)
        reasons.append("skipped_block_gaps")
    if crop_count == 0:
        score += 90
        reasons.append("zero_crops")
    elif crop_count < max(3, int(median_crops * 0.25)):
        score += 40
        reasons.append("low_crop_count")
    elif crop_count > max(50, int(median_crops * 2.5)):
        score += 30
        reasons.append("high_crop_density")
    return score, reasons


def build_coverage_review(private_root: Path) -> dict[str, Any]:
    """Build overlays + coverage queue for every page with a result JSON."""

    ensure_layout(private_root)
    block_summary = audit_block_coverage(private_root)
    block_rows = read_jsonl(
        manifest_path(private_root, "block-coverage-audit.jsonl"), BlockCoverageRecord
    )
    gaps_by_page: dict[str, int] = Counter(
        r.opaque_page_reference for r in block_rows if r.requires_human_coverage_review
    )

    sources = {
        s.page_id: s
        for s in read_jsonl(manifest_path(private_root, "source-manifest.jsonl"), SourceRecord)
    }
    documents = {
        d.document_id: d
        for d in read_jsonl(manifest_path(private_root, "document-manifest.jsonl"), DocumentRecord)
    }
    crops = read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
    crops_by_page: dict[str, list[CropRecord]] = {}
    for crop in crops:
        crops_by_page.setdefault(crop.page_id, []).append(crop)

    pages = pages_dir(private_root)
    result_files = sorted(pages.glob("*.result.json")) if pages.is_dir() else []
    crop_counts = [
        len(crops_by_page.get(p.name.replace(".result.json", ""), [])) for p in result_files
    ]
    median_crops = 0.0
    if crop_counts:
        ordered = sorted(crop_counts)
        mid = len(ordered) // 2
        median_crops = (
            float(ordered[mid])
            if len(ordered) % 2 == 1
            else (ordered[mid - 1] + ordered[mid]) / 2.0
        )

    cov_root = coverage_dir(private_root)
    cov_root.mkdir(parents=True, exist_ok=True)
    entries: list[CoverageQueueEntry] = []
    overlays = 0
    for result_path in result_files:
        page_id = result_path.name.replace(".result.json", "")
        image_path = pages / f"{page_id}.png"
        if not image_path.is_file():
            continue
        data = json.loads(result_path.read_text(encoding="utf-8"))
        blocks = [b for b in (data.get("blocks") or []) if isinstance(b, dict)]
        # Only outline skipped blocks that need human review (gaps).
        gap_indices = {
            r.block_index
            for r in block_rows
            if r.opaque_page_reference == page_id and r.requires_human_coverage_review
        }
        skipped_bboxes = [
            b["bbox"]
            for i, b in enumerate(blocks)
            if i in gap_indices and isinstance(b.get("bbox"), dict)
        ]
        page_crops = crops_by_page.get(page_id, [])
        out_path = cov_root / f"{page_id}.overlay.png"
        build_page_overlay(
            page_image_path=image_path,
            page_result_path=result_path,
            crops=page_crops,
            out_path=out_path,
            skipped_block_bboxes=skipped_bboxes,
        )
        overlays += 1
        source = sources.get(page_id)
        doc = documents.get(source.document_id) if source else None
        gap_count = gaps_by_page.get(page_id, 0)
        score, reasons = _priority_for_page(
            source=source,
            document=doc,
            crop_count=len(page_crops),
            gap_count=gap_count,
            median_crops=median_crops,
        )
        entries.append(
            CoverageQueueEntry(
                opaque_page_reference=page_id,
                opaque_document_reference=(
                    source.document_id if source is not None else "doc_unknown"
                ),
                queue_index=0,
                priority_score=score,
                priority_reasons=reasons,
                crop_count=len(page_crops),
                skipped_block_gap_count=gap_count,
            )
        )

    entries.sort(
        key=lambda e: (-e.priority_score, e.opaque_page_reference, e.opaque_document_reference)
    )
    for i, entry in enumerate(entries):
        entry.queue_index = i

    payload = json.dumps(
        [e.model_dump(mode="json") for e in entries],
        sort_keys=True,
        separators=(",", ":"),
    )
    content_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    manifest = CoverageQueueManifest(
        queue_version=COVERAGE_QUEUE_VERSION,
        created_at=_now(),
        page_count=len(entries),
        content_sha256=content_sha,
        entries=entries,
        manual_region_status="not_yet_human_verified",
    )
    write_jsonl_atomic(manifest_path(private_root, "coverage-queue.jsonl"), [manifest])
    # Ensure coverage-events file exists empty (do not fabricate events).
    events_path = manifest_path(private_root, "coverage-events.jsonl")
    if not events_path.exists():
        events_path.write_text("", encoding="utf-8")

    summary = {
        "queue_version": COVERAGE_QUEUE_VERSION,
        "page_count": len(entries),
        "overlays_written": overlays,
        "content_sha256": content_sha,
        "manual_region_status": "not_yet_human_verified",
        "block_coverage": block_summary,
        "pages_with_low_crop_count": sum(
            1 for e in entries if "low_crop_count" in e.priority_reasons
        ),
        "pages_with_high_crop_density": sum(
            1 for e in entries if "high_crop_density" in e.priority_reasons
        ),
        "pages_with_block_gaps": sum(1 for e in entries if e.skipped_block_gap_count > 0),
        "human_coverage_events": 0,
        "note": "All pages require human coverage verification before manual-region conclusions.",
    }
    reports_dir(private_root).mkdir(parents=True, exist_ok=True)
    (reports_dir(private_root) / "coverage-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def verify_coverage_artefacts(private_root: Path) -> list[str]:
    problems: list[str] = []
    queues = read_jsonl(manifest_path(private_root, "coverage-queue.jsonl"), CoverageQueueManifest)
    if not queues:
        return ["coverage queue missing"]
    queue = queues[-1]
    cov = coverage_dir(private_root)
    for entry in queue.entries:
        overlay = cov / f"{entry.opaque_page_reference}.overlay.png"
        if not overlay.is_file():
            problems.append(f"missing overlay for page slot {entry.queue_index}")
            continue
        try:
            sha256_file(overlay)
        except OSError:
            problems.append(f"unreadable overlay at queue index {entry.queue_index}")
    return problems

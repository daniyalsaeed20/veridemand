"""Skipped-block vs child-line coverage audit (no labels; no auto-export)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.datasets.phase5.constants import (
    BLOCK_COVERAGE_GAP_THRESHOLD,
    BLOCK_COVERAGE_VERSION,
)
from backend.app.datasets.phase5.jsonl_io import read_jsonl, write_jsonl_atomic
from backend.app.datasets.phase5.paths import ensure_layout, manifest_path, pages_dir, reports_dir
from backend.app.datasets.phase5.schemas import BlockCoverageRecord, CropRecord, SourceRecord


def _bbox_area(bbox: dict[str, Any]) -> float:
    return max(0.0, float(bbox.get("width", 0.0))) * max(0.0, float(bbox.get("height", 0.0)))


def _bbox_intersection_area(a: dict[str, Any], b: dict[str, Any]) -> float:
    ax0 = float(a["x"])
    ay0 = float(a["y"])
    ax1 = ax0 + float(a["width"])
    ay1 = ay0 + float(a["height"])
    bx0 = float(b["x"])
    by0 = float(b["y"])
    bx1 = bx0 + float(b["width"])
    by1 = by0 + float(b["height"])
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def _union_coverage_ratio(block_bbox: dict[str, Any], line_bboxes: list[dict[str, Any]]) -> float:
    """Approximate block-area fraction covered by child-line bbox union (grid sample)."""

    block_area = _bbox_area(block_bbox)
    if block_area <= 0.0:
        return 1.0 if not line_bboxes else 0.0
    if not line_bboxes:
        return 0.0
    # Exact union for axis-aligned rectangles via inclusion is expensive; use fine grid.
    x0 = float(block_bbox["x"])
    y0 = float(block_bbox["y"])
    w = float(block_bbox["width"])
    h = float(block_bbox["height"])
    steps = 32
    covered = 0
    total = 0
    for i in range(steps):
        for j in range(steps):
            px = x0 + (i + 0.5) * w / steps
            py = y0 + (j + 0.5) * h / steps
            total += 1
            for lb in line_bboxes:
                lx0 = float(lb["x"])
                ly0 = float(lb["y"])
                lx1 = lx0 + float(lb["width"])
                ly1 = ly0 + float(lb["height"])
                if lx0 <= px <= lx1 and ly0 <= py <= ly1:
                    covered += 1
                    break
    return covered / total if total else 0.0


def _line_bbox_for_id(lines: list[dict[str, Any]], line_id: str) -> dict[str, Any] | None:
    for line in lines:
        if line.get("id") == line_id and isinstance(line.get("bbox"), dict):
            bbox = line["bbox"]
            return dict(bbox)
    return None


def audit_block_coverage(private_root: Path) -> dict[str, Any]:
    """Audit skipped blocks against child lines / exported crops."""

    ensure_layout(private_root)
    sources = {
        s.page_id: s
        for s in read_jsonl(manifest_path(private_root, "source-manifest.jsonl"), SourceRecord)
    }
    crops = read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
    crops_by_page: dict[str, list[CropRecord]] = {}
    for crop in crops:
        crops_by_page.setdefault(crop.page_id, []).append(crop)

    records: list[BlockCoverageRecord] = []
    pages = pages_dir(private_root)
    result_files = sorted(pages.glob("*.result.json")) if pages.is_dir() else []
    skipped_blocks = 0
    fully_represented = 0
    with_gaps = 0

    for result_path in result_files:
        page_id = result_path.name.replace(".result.json", "")
        source = sources.get(page_id)
        data = json.loads(result_path.read_text(encoding="utf-8"))
        lines = [x for x in (data.get("lines") or []) if isinstance(x, dict)]
        blocks = [x for x in (data.get("blocks") or []) if isinstance(x, dict)]
        page_crops = crops_by_page.get(page_id, [])
        # Batch export skips blocks; every block is a skipped export candidate.
        for bi, block in enumerate(blocks):
            skipped_blocks += 1
            bbox = block.get("bbox") if isinstance(block.get("bbox"), dict) else None
            if bbox is None:
                continue
            line_ids = [str(x) for x in (block.get("line_ids") or [])]
            child_bboxes: list[dict[str, Any]] = []
            for lid in line_ids:
                lb = _line_bbox_for_id(lines, lid)
                if lb is not None:
                    child_bboxes.append(lb)
            # Fallback: if no line_ids, treat equal-geometry lines as children.
            if not child_bboxes:
                for line in lines:
                    lb = line.get("bbox")
                    if not isinstance(lb, dict):
                        continue
                    if abs(_bbox_intersection_area(bbox, lb) - _bbox_area(bbox)) < 1e-9:
                        child_bboxes.append(lb)
            ratio = _union_coverage_ratio(bbox, child_bboxes)
            child_crop_exists = False
            for crop in page_crops:
                sb = crop.source_bbox
                crop_bbox = {
                    "x": sb.x,
                    "y": sb.y,
                    "width": sb.width,
                    "height": sb.height,
                }
                for lb in child_bboxes:
                    if _bbox_intersection_area(crop_bbox, lb) > 0.5 * _bbox_area(lb):
                        child_crop_exists = True
                        break
                if child_crop_exists:
                    break
            gap = ratio < BLOCK_COVERAGE_GAP_THRESHOLD or (
                len(child_bboxes) == 0 and _bbox_area(bbox) > 0
            )
            requires = gap or not child_crop_exists
            if requires:
                with_gaps += 1
            else:
                fully_represented += 1
            records.append(
                BlockCoverageRecord(
                    opaque_page_reference=page_id,
                    opaque_document_reference=(
                        source.document_id if source is not None else "doc_unknown"
                    ),
                    block_index=bi,
                    child_line_count=len(child_bboxes),
                    child_crop_exists=child_crop_exists,
                    union_coverage_ratio=round(ratio, 6),
                    coverage_gap=gap,
                    requires_human_coverage_review=requires,
                )
            )

    write_jsonl_atomic(manifest_path(private_root, "block-coverage-audit.jsonl"), records)
    summary = {
        "audit_version": BLOCK_COVERAGE_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "gap_threshold": BLOCK_COVERAGE_GAP_THRESHOLD,
        "skipped_block_count": skipped_blocks,
        "fully_represented_by_lines": fully_represented,
        "blocks_with_coverage_gaps": with_gaps,
        "records_written": len(records),
        "note": (
            "Populate writes 1:1 block proxies from lines; gaps should be rare. "
            "Do not auto-export blocks into the training crop set."
        ),
    }
    reports_dir(private_root).mkdir(parents=True, exist_ok=True)
    (reports_dir(private_root) / "block-coverage-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary

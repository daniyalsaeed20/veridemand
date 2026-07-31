"""Manual-region worklist writer (opaque IDs only)."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.datasets.phase5.jsonl_io import read_jsonl
from backend.app.datasets.phase5.paths import manifest_path, reports_dir
from backend.app.datasets.phase5.schemas import CropRecord, SourceRecord


def write_manual_region_worklist(private_root: Path) -> tuple[Path, int]:
    """Flag pages with zero exported crops for later human geometry."""

    sources = read_jsonl(manifest_path(private_root, "source-manifest.jsonl"), SourceRecord)
    crops = read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
    pages_with_crops = {c.page_id for c in crops}
    rows: list[dict[str, object]] = []
    for source in sources:
        if source.page_id in pages_with_crops:
            continue
        rows.append(
            {
                "document_id": source.document_id,
                "page_id": source.page_id,
                "page_index": source.page_index,
                "reason": "zero_exported_candidates",
            }
        )
    out = reports_dir(private_root) / "manual-region-worklist.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return out, len(rows)

"""Export all geometry-ready pages under the private phase5 pages/ tree."""

from __future__ import annotations

from pathlib import Path

from backend.app.datasets.phase5.export import export_from_phase4_json
from backend.app.datasets.phase5.jsonl_io import read_jsonl
from backend.app.datasets.phase5.paths import manifest_path, pages_dir
from backend.app.datasets.phase5.schemas import CropRecord, SourceRecord


def export_all_populated_pages(private_root: Path) -> dict[str, int]:
    """Export crops for every ``pages/{page_id}.result.json`` with matching PNG."""

    sources = {
        s.page_id: s
        for s in read_jsonl(manifest_path(private_root, "source-manifest.jsonl"), SourceRecord)
    }
    before = len(read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord))
    created_total = 0
    skipped = 0
    failures = 0
    pages = pages_dir(private_root)
    if not pages.is_dir():
        return {
            "pages_seen": 0,
            "crops_created": 0,
            "crops_before": before,
            "crops_after": before,
            "failures": 0,
        }
    result_files = sorted(pages.glob("*.result.json"))
    for result_path in result_files:
        page_id = result_path.name.replace(".result.json", "")
        image_path = pages / f"{page_id}.png"
        if not image_path.is_file():
            failures += 1
            continue
        source = sources.get(page_id)
        try:
            # Lines cover full_page_ocr geometry. Populate writes 1:1 block proxies
            # from lines; exporting both would duplicate every region.
            created = export_from_phase4_json(
                private_root=private_root,
                page_result_path=result_path,
                page_image_path=image_path,
                source_group_id=source.source_group_id if source else None,
                document_id=source.document_id if source else None,
                page_id=page_id,
                kinds={"lines", "repair_regions"},
            )
            if created:
                created_total += len(created)
            else:
                skipped += 1
        except Exception:
            failures += 1
    after = len(read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord))
    return {
        "pages_seen": len(result_files),
        "crops_created": created_total,
        "pages_unchanged": skipped,
        "crops_before": before,
        "crops_after": after,
        "failures": failures,
    }

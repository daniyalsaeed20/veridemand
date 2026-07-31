"""Offline page render + OCR geometry populate for Phase 5 private crops.

Writes gitignored page PNGs and geometry-only page-result JSON under the
private phase5 root. Never logs OCR text or private filenames.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _ensure_path() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def strip_and_write_result(path: Path, payload: dict[str, Any]) -> None:
    from backend.app.datasets.phase5.geometry_strip import strip_text_fields

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(strip_text_fields(payload), indent=2) + "\n", encoding="utf-8")


def populate_document(
    *,
    private_root: Path,
    fixtures_private: Path,
    document: Any,
    adapter: Any,
    max_pages: int | None,
) -> dict[str, int]:
    """Render + OCR one registered document. Returns opaque aggregate counts."""

    import pypdfium2 as pdfium
    from backend.app.datasets.phase5.ids import new_page_id
    from backend.app.datasets.phase5.jsonl_io import append_jsonl, read_jsonl
    from backend.app.datasets.phase5.paths import manifest_path
    from backend.app.datasets.phase5.schemas import SourceRecord
    from backend.app.extraction.visual.coordinates import map_pixel_polygon
    from backend.app.extraction.visual.renderer import RenderLimits, render_page
    from PIL import Image

    stats = {"pages": 0, "pages_with_geometry": 0, "lines": 0, "words": 0, "failures": 0}
    pdf_path = (fixtures_private / document.source_relpath).resolve()
    try:
        pdf_path.relative_to(fixtures_private.resolve())
    except ValueError:
        stats["failures"] += 1
        return stats
    if not pdf_path.is_file():
        stats["failures"] += 1
        return stats

    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        page_count = len(doc)
        limit = page_count if max_pages is None else min(page_count, max_pages)
        existing_by_page_id = {
            s.page_id: s
            for s in read_jsonl(manifest_path(private_root, "source-manifest.jsonl"), SourceRecord)
            if s.document_id == document.document_id
        }
        existing_by_index = {s.page_index: s for s in existing_by_page_id.values()}
        limits = RenderLimits(
            target_dpi=200.0,
            min_effective_dpi=120.0,
            max_render_pixels=40_000_000,
            max_render_side_pixels=6000,
            dimension_tolerance_points=1.0,
        )
        for page_index in range(limit):
            page_number = page_index + 1
            # Reuse page_id if already registered for this index.
            prior = existing_by_index.get(page_index)
            page_id = prior.page_id if prior is not None else new_page_id()
            page = doc[page_index]
            width_pt, height_pt = page.get_size()
            try:
                rendered = render_page(
                    pdf_path,
                    page_number=page_number,
                    page_width_points=float(width_pt),
                    page_height_points=float(height_pt),
                    limits=limits,
                    pdf_document=doc,
                )
            except Exception:
                stats["failures"] += 1
                continue
            image: Image.Image = rendered.image
            png_rel = f"pages/{page_id}.png"
            result_rel = f"pages/{page_id}.result.json"
            png_path = private_root / png_rel
            png_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(png_path, format="PNG", optimize=True)

            try:
                raw_lines = adapter.recognise(image)
            except Exception:
                raw_lines = []
                stats["failures"] += 1

            lines_out: list[dict[str, Any]] = []
            words_out: list[dict[str, Any]] = []
            w_px, h_px = image.size
            for li, raw in enumerate(raw_lines):
                try:
                    mapped = map_pixel_polygon(
                        raw.polygon_px, width_pixels=w_px, height_pixels=h_px
                    )
                except Exception:
                    continue
                lines_out.append(
                    {
                        "id": f"line_{li:06d}",
                        "bbox": mapped.bbox.model_dump(),
                        "polygon": mapped.polygon.model_dump(),
                    }
                )
                for wi, raw_word in enumerate(raw.words or []):
                    try:
                        wm = map_pixel_polygon(
                            raw_word.polygon_px, width_pixels=w_px, height_pixels=h_px
                        )
                    except Exception:
                        continue
                    words_out.append(
                        {
                            "id": f"word_{li:06d}_{wi:06d}",
                            "bbox": wm.bbox.model_dump(),
                            "polygon": wm.polygon.model_dump(),
                        }
                    )

            # Lightweight block proxies from lines (geometry only).
            blocks_out = [
                {
                    "id": f"block_{i:06d}",
                    "bbox": line["bbox"],
                    "polygon": line["polygon"],
                    "line_ids": [line["id"]],
                    "page_number": page_number,
                    "sequence_index": i,
                    "block_type": "text_unknown",
                    "reading_order_index": i,
                    "reading_order_status": "provisional_phase_4",
                }
                for i, line in enumerate(lines_out)
            ]

            result = {
                "page_number": page_number,
                "status": "completed",
                "source_mode": "visual_ocr",
                "render_width_pixels": w_px,
                "render_height_pixels": h_px,
                "lines": lines_out,
                "words": words_out,
                "blocks": blocks_out,
                "repair_regions": [],
            }
            strip_and_write_result(private_root / result_rel, result)

            # Never append a second SourceRecord for an existing page_id or page_index.
            if prior is None and page_id not in existing_by_page_id:
                record = SourceRecord(
                    source_group_id=document.source_group_id,
                    document_id=document.document_id,
                    page_id=page_id,
                    page_index=page_index,
                    page_width_px=w_px,
                    page_height_px=h_px,
                    page_relpath=png_rel.replace("\\", "/"),
                    source_family=document.source_family,
                    document_sha256=document.document_sha256,
                    page_count=document.page_count,
                    created_at=datetime.now(UTC),
                )
                append_jsonl(
                    manifest_path(private_root, "source-manifest.jsonl"),
                    [record],
                )
                existing_by_page_id[page_id] = record
                existing_by_index[page_index] = record
            stats["pages"] += 1
            if lines_out or words_out:
                stats["pages_with_geometry"] += 1
            stats["lines"] += len(lines_out)
            stats["words"] += len(words_out)
            print(
                f"populated document_id={document.document_id} page_index={page_index} "
                f"lines={len(lines_out)} words={len(words_out)}"
            )
    finally:
        doc.close()
    return stats


def main(argv: list[str] | None = None) -> int:
    _ensure_path()
    parser = argparse.ArgumentParser(description="Populate Phase 5 private page evidence")
    parser.add_argument("--root", default=None)
    parser.add_argument(
        "--fixtures-private",
        default=str(ROOT / "fixtures" / "private"),
        help="Approved fixtures/private root",
    )
    parser.add_argument("--max-pages", type=int, default=None)
    args = parser.parse_args(argv)

    from backend.app.datasets.phase5.jsonl_io import read_jsonl
    from backend.app.datasets.phase5.paths import default_private_root, ensure_layout, manifest_path
    from backend.app.datasets.phase5.schemas import DocumentRecord
    from backend.app.extraction.visual.paddle_adapter import PaddleOcrAdapter
    from backend.app.settings.config import Settings

    private_root = Path(args.root) if args.root else default_private_root()
    fixtures_private = Path(args.fixtures_private)
    ensure_layout(private_root)
    documents = read_jsonl(manifest_path(private_root, "document-manifest.jsonl"), DocumentRecord)
    if not documents:
        print("No registered documents; run register-sources first", file=sys.stderr)
        return 1

    from backend.app.extraction.visual.worker_manager import VisualOcrWorkerManager

    settings = Settings()
    config = VisualOcrWorkerManager(settings).config_from_settings()
    adapter = PaddleOcrAdapter(config)
    try:
        adapter.load()
    except Exception as exc:
        print(f"OCR runtime unavailable: {type(exc).__name__}", file=sys.stderr)
        return 3

    totals = {"pages": 0, "pages_with_geometry": 0, "lines": 0, "words": 0, "failures": 0}
    # Smaller documents first so short jobs finish before long multi-page PDFs.
    documents = sorted(documents, key=lambda d: (d.page_count, d.document_id))
    for document in documents:
        part = populate_document(
            private_root=private_root,
            fixtures_private=fixtures_private,
            document=document,
            adapter=adapter,
            max_pages=args.max_pages,
        )
        for key in totals:
            totals[key] += part[key]
    print(json.dumps({"status": "ok", **totals}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

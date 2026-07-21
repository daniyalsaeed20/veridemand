"""Build synthetic extraction fixtures (future gold inputs, no active test).

These fixtures are domain-neutral. Ground truth uses only document-extraction
concepts from the canonical specification: pages, blocks, lines, words, tables,
cells, normalized coordinates (top-left origin, [0, 1]), source modes, script
types, recognition methods, and warnings. No legal facts, critical fields, or
review-workflow states are present.

Run: python scripts/build_extraction_fixtures.py
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "extraction_acceptance"

SCHEMA_LABEL = "SYNTHETIC EXTRACTION FIXTURE — FUTURE GOLD INPUT (no active test)"
NOTES = "Synthetic fixture — no private case data"


# --------------------------------------------------------------------------- #
# Synthetic media (no third-party deps required at commit time)
# --------------------------------------------------------------------------- #
def _png_rgb(width: int, height: int, rgb: tuple[int, int, int] = (255, 255, 255)) -> bytes:
    r, g, b = rgb
    row = bytes([0]) + bytes([r, g, b] * width)
    compressed = zlib.compress(row * height, 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            len(data).to_bytes(4, "big")
            + tag
            + data
            + zlib.crc32(tag + data).to_bytes(4, "big")
        )

    ihdr = width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes([8, 2, 0, 0, 0])
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )


def _write_text_pdf(path: Path, lines: list[str], *, width: int = 400, height: int = 500) -> None:
    parts = ["BT /F1 12 Tf"]
    y = height - 40
    for line in lines:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        parts.append(f"1 0 0 1 50 {y} Tm ({safe}) Tj")
        y -= 18
    parts.append("ET")
    _emit_pdf(path, "\n".join(parts).encode("latin-1", errors="replace"), width, height)


def _write_two_column_pdf(path: Path, width: int = 500, height: int = 400) -> None:
    parts = ["BT /F1 11 Tf"]
    left = ["Column A line 1", "Column A line 2", "Column A line 3"]
    right = ["Column B line 1", "Column B line 2", "Column B line 3"]
    y = height - 50
    for line in left:
        parts.append(f"1 0 0 1 40 {y} Tm ({line}) Tj")
        y -= 20
    y = height - 50
    for line in right:
        parts.append(f"1 0 0 1 280 {y} Tm ({line}) Tj")
        y -= 20
    parts.append("ET")
    _emit_pdf(path, "\n".join(parts).encode("latin-1"), width, height)


def _emit_pdf(path: Path, stream: bytes, width: int, height: int) -> None:
    objects: list[bytes] = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        (
            f"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
        ).encode(),
        f"4 0 obj<< /Length {len(stream)} >>stream\n".encode() + stream + b"\nendstream\nendobj\n",
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(
        f"trailer<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(bytes(out))


# --------------------------------------------------------------------------- #
# Ground-truth builders (canonical extraction concepts only)
# --------------------------------------------------------------------------- #
def _quad(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [
        [round(x0, 4), round(y0, 4)],
        [round(x1, 4), round(y0, 4)],
        [round(x1, 4), round(y1, 4)],
        [round(x0, 4), round(y1, 4)],
    ]


class _Ids:
    def __init__(self) -> None:
        self.word = 0
        self.line = 0
        self.block = 0


def _word(
    ids: _Ids,
    text: str,
    box: tuple[float, float, float, float],
    *,
    script: str = "printed",
    method: str = "native",
) -> dict[str, Any]:
    x0, y0, x1, y1 = box
    w = {
        "id": f"word_p1_{ids.word:03d}",
        "text": text,
        "reading_order": ids.word,
        "script_type": script,
        "recognition_method": method,
        "polygon_normalized": _quad(x0, y0, x1, y1),
    }
    ids.word += 1
    return w


def _line_from_text(
    ids: _Ids,
    text: str,
    *,
    y: float,
    x_start: float = 0.08,
    x_end: float = 0.92,
    height: float = 0.04,
    script: str = "printed",
    method: str = "native",
) -> dict[str, Any]:
    tokens = text.split()
    n = max(len(tokens), 1)
    span = (x_end - x_start) / n
    words = []
    for i, tok in enumerate(tokens):
        x0 = x_start + span * i
        x1 = x_start + span * (i + 1) - 0.01
        words.append(_word(ids, tok, (x0, y, x1, y + height), script=script, method=method))
    line = {"id": f"line_p1_{ids.line:03d}", "reading_order": ids.line, "words": words}
    ids.line += 1
    return line


def _block(ids: _Ids, block_type: str, lines: list[dict[str, Any]]) -> dict[str, Any]:
    block = {
        "id": f"block_p1_{ids.block:03d}",
        "type": block_type,
        "reading_order": ids.block,
        "lines": lines,
    }
    ids.block += 1
    return block


def _page_gt(
    fixture_id: str,
    *,
    source_mode: str,
    blocks: list[dict[str, Any]],
    expected_text: str,
    rotation: int = 0,
    warnings: list[str] | None = None,
    tables: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    gt: dict[str, Any] = {
        "fixture_id": fixture_id,
        "schema_label": SCHEMA_LABEL,
        "page_number": 1,
        "source_mode": source_mode,
        "rotation_degrees": rotation,
        "expected_text": expected_text,
        "blocks": blocks,
        "warnings": warnings or [],
        "notes": NOTES,
    }
    if tables is not None:
        gt["tables"] = tables
    return gt


def _write_gt(fixture_id: str, gt: dict[str, Any]) -> None:
    (OUT / f"{fixture_id}.ground_truth.json").write_text(
        json.dumps(gt, indent=2) + "\n", encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# Fixture definitions
# --------------------------------------------------------------------------- #
def build_all() -> list[str]:
    OUT.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    def paragraph(fixture_id: str, lines: list[str], **page_kwargs: Any) -> None:
        ids = _Ids()
        line_objs = [
            _line_from_text(ids, text, y=0.10 + i * 0.06, **_line_kwargs(page_kwargs))
            for i, text in enumerate(lines)
        ]
        blocks = [_block(ids, page_kwargs.get("block_type", "paragraph"), line_objs)]
        _write_gt(
            fixture_id,
            _page_gt(
                fixture_id,
                source_mode=page_kwargs["source_mode"],
                blocks=blocks,
                expected_text="\n".join(lines),
                rotation=page_kwargs.get("rotation", 0),
                warnings=page_kwargs.get("warnings"),
            ),
        )
        created.append(fixture_id)

    # 1 clean native paragraph
    fid = "clean_native_paragraph"
    lines = [
        "This is a clean native paragraph for extraction acceptance.",
        "Second sentence stays in reading order.",
    ]
    _write_text_pdf(OUT / f"{fid}.pdf", lines)
    paragraph(fid, lines, source_mode="native_authority")

    # 2 two-column
    fid = "two_column_page"
    _write_two_column_pdf(OUT / f"{fid}.pdf")
    ids = _Ids()
    left_lines = ["Column A line 1", "Column A line 2", "Column A line 3"]
    right_lines = ["Column B line 1", "Column B line 2", "Column B line 3"]
    left_block = _block(
        ids,
        "paragraph",
        [_line_from_text(ids, t, y=0.12 + i * 0.08, x_start=0.06, x_end=0.46)
         for i, t in enumerate(left_lines)],
    )
    right_block = _block(
        ids,
        "paragraph",
        [_line_from_text(ids, t, y=0.12 + i * 0.08, x_start=0.54, x_end=0.94)
         for i, t in enumerate(right_lines)],
    )
    _write_gt(
        fid,
        _page_gt(
            fid,
            source_mode="native_authority",
            blocks=[left_block, right_block],
            expected_text="\n".join(left_lines + right_lines),
        ),
    )
    created.append(fid)

    # 3 table
    fid = "table_page"
    table_lines = ["Item Qty Amount", "Alpha 1 10.00", "Beta 2 20.00"]
    _write_text_pdf(OUT / f"{fid}.pdf", table_lines)
    ids = _Ids()
    table_block = _block(
        ids,
        "table",
        [_line_from_text(ids, t, y=0.12 + i * 0.10) for i, t in enumerate(table_lines)],
    )
    grid = [row.split() for row in table_lines]
    cells = []
    for r, row in enumerate(grid):
        for c, text in enumerate(row):
            cells.append(
                {
                    "row": r,
                    "column": c,
                    "text": text,
                    "polygon_normalized": _quad(
                        0.10 + c * 0.25, 0.12 + r * 0.10, 0.32 + c * 0.25, 0.20 + r * 0.10
                    ),
                }
            )
    tables = [{"id": "table_p1_000", "row_count": len(grid), "column_count": 3, "cells": cells}]
    _write_gt(
        fid,
        _page_gt(
            fid,
            source_mode="native_authority",
            blocks=[table_block],
            expected_text="\n".join(table_lines),
            tables=tables,
        ),
    )
    created.append(fid)

    # 4 label/value form
    fid = "label_value_form"
    form_lines = ["Person Name: Jordan Lee", "File ID: ID-10042", "Event Date: 2024-01-15"]
    _write_text_pdf(OUT / f"{fid}.pdf", form_lines)
    ids = _Ids()
    form_block = _block(
        ids,
        "key_value",
        [_line_from_text(ids, t, y=0.12 + i * 0.08) for i, t in enumerate(form_lines)],
    )
    _write_gt(
        fid,
        _page_gt(
            fid,
            source_mode="native_authority",
            blocks=[form_block],
            expected_text="\n".join(form_lines),
        ),
    )
    created.append(fid)

    # 5 header/footer (domain-neutral organisation name)
    fid = "header_footer_page"
    hf_lines = [
        "HEADER North Harbor Records Department",
        "Body paragraph one.",
        "Body paragraph two.",
        "FOOTER Page 1 of 1",
    ]
    _write_text_pdf(OUT / f"{fid}.pdf", hf_lines)
    ids = _Ids()
    blocks = [
        _block(ids, "header", [_line_from_text(ids, hf_lines[0], y=0.06)]),
        _block(
            ids,
            "paragraph",
            [_line_from_text(ids, hf_lines[1], y=0.30), _line_from_text(ids, hf_lines[2], y=0.38)],
        ),
        _block(ids, "footer", [_line_from_text(ids, hf_lines[3], y=0.92)]),
    ]
    _write_gt(
        fid,
        _page_gt(
            fid,
            source_mode="native_authority",
            blocks=blocks,
            expected_text="\n".join(hf_lines),
        ),
    )
    created.append(fid)

    # 6 rotated text
    fid = "rotated_text_page"
    _write_text_pdf(OUT / f"{fid}.pdf", ["Rotated challenge line ALPHA"])
    ids = _Ids()
    blocks = [_block(ids, "paragraph", [_line_from_text(ids, "Rotated challenge line ALPHA", y=0.45)])]
    _write_gt(
        fid,
        _page_gt(
            fid,
            source_mode="native_authority",
            blocks=blocks,
            expected_text="Rotated challenge line ALPHA",
            rotation=90,
            warnings=["page_rotation_detected"],
        ),
    )
    created.append(fid)

    # 7 skewed scan (image)
    fid = "skewed_scan_page"
    (OUT / f"{fid}.png").write_bytes(_png_rgb(200, 200, (240, 240, 240)))
    ids = _Ids()
    blocks = [
        _block(
            ids,
            "paragraph",
            [_line_from_text(ids, "SKEW SAMPLE", y=0.40, method="paddle_ocr")],
        )
    ]
    _write_gt(
        fid,
        _page_gt(
            fid,
            source_mode="image_authority",
            blocks=blocks,
            expected_text="SKEW SAMPLE",
            warnings=["deskew_applied"],
        ),
    )
    created.append(fid)

    # 8 image-only, no text layer
    fid = "image_only_no_text_layer"
    (OUT / f"{fid}.png").write_bytes(_png_rgb(180, 180, (250, 250, 250)))
    ids = _Ids()
    blocks = [
        _block(
            ids,
            "paragraph",
            [_line_from_text(ids, "TYPED SCAN LINE", y=0.20, method="paddle_ocr")],
        )
    ]
    _write_gt(
        fid,
        _page_gt(
            fid,
            source_mode="image_authority",
            blocks=blocks,
            expected_text="TYPED SCAN LINE",
        ),
    )
    created.append(fid)

    # 9 image with correct hidden OCR (trusted native/embedded text)
    fid = "image_with_correct_hidden_ocr"
    _write_text_pdf(OUT / f"{fid}.pdf", ["HIDDEN OCR CORRECT"])
    ids = _Ids()
    blocks = [_block(ids, "paragraph", [_line_from_text(ids, "HIDDEN OCR CORRECT", y=0.15)])]
    _write_gt(
        fid,
        _page_gt(
            fid,
            source_mode="native_authority",
            blocks=blocks,
            expected_text="HIDDEN OCR CORRECT",
        ),
    )
    created.append(fid)

    # 10 corrupt hidden OCR: native rejected, rendered pixels authoritative
    fid = "corrupt_hidden_ocr"
    _write_text_pdf(OUT / f"{fid}.pdf", ["Badge ID Go1s"])  # misleading embedded text
    ids = _Ids()
    blocks = [
        _block(
            ids,
            "paragraph",
            [_line_from_text(ids, "Badge ID A1234", y=0.15, method="paddle_ocr")],
        )
    ]
    _write_gt(
        fid,
        _page_gt(
            fid,
            source_mode="visual_authority",
            blocks=blocks,
            expected_text="Badge ID A1234",
            warnings=["native_text_rejected", "visual_text_disagreement"],
        ),
    )
    created.append(fid)

    # 11 boxed individual characters
    fid = "boxed_individual_characters"
    _write_text_pdf(OUT / f"{fid}.pdf", ["A B C D"])
    ids = _Ids()
    chars = ["A", "B", "C", "D"]
    words = [
        _word(ids, ch, (0.10 + i * 0.15, 0.40, 0.20 + i * 0.15, 0.50)) for i, ch in enumerate(chars)
    ]
    blocks = [_block(ids, "paragraph", [{"id": "line_p1_000", "reading_order": 0, "words": words}])]
    _write_gt(
        fid,
        _page_gt(
            fid,
            source_mode="native_authority",
            blocks=blocks,
            expected_text="A B C D",
        ),
    )
    created.append(fid)

    # 12 mixed printed + handwritten-like (hybrid page)
    fid = "mixed_print_handwritten_like"
    _write_text_pdf(OUT / f"{fid}.pdf", ["PRINT LABEL", "handish value xx"])
    ids = _Ids()
    printed_line = _line_from_text(ids, "PRINT LABEL", y=0.15, method="paddle_ocr")
    hand_line = _line_from_text(
        ids, "handish value xx", y=0.30, script="handwritten", method="openai_vision"
    )
    blocks = [_block(ids, "key_value", [printed_line, hand_line])]
    _write_gt(
        fid,
        _page_gt(
            fid,
            source_mode="hybrid_authority",
            blocks=blocks,
            expected_text="PRINT LABEL\nhandish value xx",
            warnings=["handwritten_region_detected"],
        ),
    )
    created.append(fid)

    # 13 diagram grid labels (figure with non-text regions)
    fid = "diagram_grid_labels"
    _write_text_pdf(OUT / f"{fid}.pdf", ["N", "E", "S", "W", "GRID"])
    ids = _Ids()
    labels = ["N", "E", "S", "W", "GRID"]
    words = [
        _word(ids, t, (0.10 + i * 0.12, 0.10, 0.18 + i * 0.12, 0.18)) for i, t in enumerate(labels)
    ]
    blocks = [_block(ids, "figure", [{"id": "line_p1_000", "reading_order": 0, "words": words}])]
    _write_gt(
        fid,
        _page_gt(
            fid,
            source_mode="native_authority",
            blocks=blocks,
            expected_text="N E S W GRID",
            warnings=["non_text_regions_present"],
        ),
    )
    created.append(fid)

    # 14 overlapping duplicate hidden text (deduplicated output)
    fid = "overlapping_duplicate_hidden_text"
    _write_text_pdf(OUT / f"{fid}.pdf", ["DUPLICATE LINE", "DUPLICATE LINE"])
    ids = _Ids()
    blocks = [_block(ids, "paragraph", [_line_from_text(ids, "DUPLICATE LINE", y=0.15)])]
    _write_gt(
        fid,
        _page_gt(
            fid,
            source_mode="native_authority",
            blocks=blocks,
            expected_text="DUPLICATE LINE",
            warnings=["duplicate_text_layer_detected"],
        ),
    )
    created.append(fid)

    # 15 date and identifier fields
    fid = "date_identifier_fields"
    di_lines = ["Date 2024-01-15", "ID ID-10042"]
    _write_text_pdf(OUT / f"{fid}.pdf", di_lines)
    ids = _Ids()
    blocks = [
        _block(
            ids,
            "key_value",
            [_line_from_text(ids, t, y=0.15 + i * 0.12) for i, t in enumerate(di_lines)],
        )
    ]
    _write_gt(
        fid,
        _page_gt(
            fid,
            source_mode="native_authority",
            blocks=blocks,
            expected_text="\n".join(di_lines),
        ),
    )
    created.append(fid)

    _write_manifest(created)
    return created


def _line_kwargs(page_kwargs: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "script" in page_kwargs:
        out["script"] = page_kwargs["script"]
    if "method" in page_kwargs:
        out["method"] = page_kwargs["method"]
    return out


def _write_manifest(created: list[str]) -> None:
    manifest = {
        "schema_label": SCHEMA_LABEL,
        "purpose": "Future gold inputs for the document-extraction platform. No active test consumes these.",
        "concepts": [
            "documents",
            "pages",
            "blocks",
            "lines",
            "words",
            "tables",
            "cells",
            "coordinates_normalized_top_left",
            "source_modes",
            "script_types",
            "recognition_methods",
            "warnings",
        ],
        "fixture_count": len(created),
        "fixtures": created,
        "note": "Synthetic only — no private case names or values.",
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Synthetic extraction fixtures\n\n"
        "Domain-neutral synthetic fixtures for the document-extraction platform.\n"
        "No real client names, case numbers, or private hashes.\n\n"
        "These are **future gold inputs**: no active test consumes them yet. Ground truth\n"
        "uses only extraction concepts (pages, blocks, lines, words, tables, cells,\n"
        "normalized coordinates, source modes, script types, recognition methods, warnings).\n\n"
        "Rebuild with: `python scripts/build_extraction_fixtures.py`\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    ids = build_all()
    print(f"built {len(ids)} fixtures -> {OUT}")

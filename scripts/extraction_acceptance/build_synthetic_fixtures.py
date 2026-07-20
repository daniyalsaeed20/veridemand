"""Build safe synthetic extraction-acceptance fixtures (no private case data)."""

from __future__ import annotations

import json
import math
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "fixtures" / "extraction_acceptance"


def _png_rgb(width: int, height: int, rgb: tuple[int, int, int] = (255, 255, 255)) -> bytes:
    """Minimal uncompressed-looking PNG via zlib (no PIL required for commit)."""
    r, g, b = rgb
    raw = b""
    row = bytes([0]) + bytes([r, g, b] * width)
    raw = row * height
    compressed = zlib.compress(raw, 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            len(data).to_bytes(4, "big")
            + tag
            + data
            + zlib.crc32(tag + data).to_bytes(4, "big")
        )

    ihdr = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + bytes([8, 2, 0, 0, 0])
    )
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(
        b"IEND", b""
    )


def _write_text_pdf(path: Path, lines: list[str], *, width: int = 400, height: int = 500) -> None:
    y = height - 40
    content_parts = ["BT /F1 12 Tf"]
    for line in lines:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_parts.append(f"50 {y} Td ({safe}) Tj")
        content_parts.append("0 -18 Td")
        y -= 18
    content_parts.append("ET")
    # Rebuild with absolute Td positions for simplicity
    content_parts = ["BT /F1 12 Tf"]
    y = height - 40
    for line in lines:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_parts.append(f"1 0 0 1 50 {y} Tm ({safe}) Tj")
        y -= 18
    content_parts.append("ET")
    stream = "\n".join(content_parts).encode("latin-1", errors="replace")
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


def _write_two_column_pdf(path: Path) -> None:
    # Left column then right column visually; stream paints left then right.
    width, height = 500, 400
    parts = ["BT /F1 11 Tf"]
    left = ["Column A line 1", "Column A line 2", "Column A line 3"]
    right = ["Column B line 1", "Column B line 2", "Column B line 3"]
    y = height - 50
    for line in left:
        safe = line.replace("(", "\\(").replace(")", "\\)")
        parts.append(f"1 0 0 1 40 {y} Tm ({safe}) Tj")
        y -= 20
    y = height - 50
    for line in right:
        safe = line.replace("(", "\\(").replace(")", "\\)")
        parts.append(f"1 0 0 1 280 {y} Tm ({safe}) Tj")
        y -= 20
    parts.append("ET")
    stream = "\n".join(parts).encode("latin-1")
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


def _quad(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _gt(
    fixture_id: str,
    *,
    transcript: str,
    lines: list[str],
    words: list[dict],
    expected_layer: str,
    review_status: str,
    extra: dict | None = None,
) -> dict:
    payload = {
        "fixture_id": fixture_id,
        "annotation_status": "human_approved",
        "page_number": 1,
        "expected_transcript": transcript,
        "expected_lines": lines,
        "expected_line_ids": [f"L{i}" for i in range(len(lines))],
        "expected_word_ids": [w["word_id"] for w in words],
        "expected_words": words,
        "expected_layer": expected_layer,
        "expected_outcome": review_status,
        "expected_rotation": 0,
        "native_trustworthy": expected_layer == "native_pdf_text",
        "corrupt_embedded": False,
        "must_reject_corrupt": False,
        "ocr_required": expected_layer == "fresh_ocr",
        "silent_mix": False,
        "critical_fields": [],
        "notes": "Synthetic fixture — no private case data",
    }
    if extra:
        payload.update(extra)
    return payload


def build_all() -> list[str]:
    OUT.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    # 1 clean native paragraph
    fid = "clean_native_paragraph"
    path = OUT / f"{fid}.pdf"
    lines = [
        "This is a clean native paragraph for extraction acceptance.",
        "Second sentence stays in reading order.",
    ]
    _write_text_pdf(path, lines)
    words = []
    order = 0
    for li, line in enumerate(lines):
        for w in line.split():
            words.append(
                {
                    "word_id": f"W{order}",
                    "text": w,
                    "reading_order": order,
                    "polygon": _quad(0.1, 0.1 + li * 0.05, 0.9, 0.14 + li * 0.05),
                }
            )
            order += 1
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="\n".join(lines),
                lines=lines,
                words=words,
                expected_layer="native_pdf_text",
                review_status="faithful_canonical",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    # 2 two-column
    fid = "two_column_page"
    _write_two_column_pdf(OUT / f"{fid}.pdf")
    lines = [
        "Column A line 1",
        "Column A line 2",
        "Column A line 3",
        "Column B line 1",
        "Column B line 2",
        "Column B line 3",
    ]
    words = [
        {
            "word_id": f"W{i}",
            "text": t,
            "reading_order": i,
            "polygon": _quad(0.05 if i < 3 else 0.55, 0.1 + (i % 3) * 0.08, 0.45 if i < 3 else 0.95, 0.16 + (i % 3) * 0.08),
            "column": 0 if i < 3 else 1,
        }
        for i, t in enumerate(lines)
    ]
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="\n".join(lines),
                lines=lines,
                words=words,
                expected_layer="native_pdf_text",
                review_status="faithful_canonical",
                extra={"layout": "two_column", "expected_column_order": [0, 0, 0, 1, 1, 1]},
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    # 3 table
    fid = "table_page"
    table_lines = [
        "Item Qty Amount",
        "Alpha 1 10.00",
        "Beta 2 20.00",
    ]
    _write_text_pdf(OUT / f"{fid}.pdf", table_lines)
    cells = ["Item", "Qty", "Amount", "Alpha", "1", "10.00", "Beta", "2", "20.00"]
    words = [
        {
            "word_id": f"W{i}",
            "text": c,
            "reading_order": i,
            "polygon": _quad(0.1 + (i % 3) * 0.25, 0.1 + (i // 3) * 0.1, 0.3 + (i % 3) * 0.25, 0.18 + (i // 3) * 0.1),
        }
        for i, c in enumerate(cells)
    ]
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="\n".join(table_lines),
                lines=table_lines,
                words=words,
                expected_layer="native_pdf_text",
                review_status="faithful_canonical",
                extra={
                    "expected_table_cells": cells,
                    "layout": "table",
                },
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    # 4 label/value form
    fid = "label_value_form"
    form_lines = ["Person Name: Jordan Lee", "File ID: ID-10042", "Event Date: 2024-01-15"]
    _write_text_pdf(OUT / f"{fid}.pdf", form_lines)
    words = []
    order = 0
    for line in form_lines:
        for w in line.replace(":", " :").split():
            words.append(
                {
                    "word_id": f"W{order}",
                    "text": w,
                    "reading_order": order,
                    "polygon": _quad(0.1, 0.1 + order * 0.02, 0.8, 0.14 + order * 0.02),
                }
            )
            order += 1
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="\n".join(form_lines),
                lines=form_lines,
                words=words,
                expected_layer="native_pdf_text",
                review_status="faithful_canonical",
                extra={
                    "expected_label_values": [
                        ["Person Name", "Jordan Lee"],
                        ["File ID", "ID-10042"],
                        ["Event Date", "2024-01-15"],
                    ],
                    "critical_fields": [
                        {
                            "field_id": "person_name",
                            "field_type": "person_name",
                            "expected": "Jordan Lee",
                            "hypothesized": "Jordan Lee",
                            "uncertain": False,
                            "accepted": True,
                            "review_required": False,
                            "layer_used": "native_pdf_text",
                        },
                        {
                            "field_id": "file_id",
                            "field_type": "id",
                            "expected": "ID-10042",
                            "hypothesized": "ID-10042",
                            "uncertain": False,
                            "accepted": True,
                            "review_required": False,
                            "layer_used": "native_pdf_text",
                        },
                    ],
                },
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    # 5 header/footer
    fid = "header_footer_page"
    hf_lines = [
        "HEADER North Harbor Legal Group, PLLC",
        "Body paragraph one.",
        "Body paragraph two.",
        "FOOTER Page 1 of 1",
    ]
    _write_text_pdf(OUT / f"{fid}.pdf", hf_lines)
    words = [
        {
            "word_id": f"W{i}",
            "text": w,
            "reading_order": i,
            "polygon": _quad(0.1, 0.05 + i * 0.05, 0.9, 0.09 + i * 0.05),
        }
        for i, w in enumerate(" ".join(hf_lines).split())
    ]
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="\n".join(hf_lines),
                lines=hf_lines,
                words=words,
                expected_layer="native_pdf_text",
                review_status="faithful_canonical",
                extra={
                    "critical_fields": [
                        {
                            "field_id": "law_firm",
                            "field_type": "law_firm_name",
                            "expected": "North Harbor Legal Group, PLLC",
                            "hypothesized": "North Harbor Legal Group, PLLC",
                            "uncertain": False,
                            "accepted": True,
                            "review_required": False,
                            "layer_used": "native_pdf_text",
                        }
                    ]
                },
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    # 6 rotated text metadata (PDF still upright; GT declares rotation challenge)
    fid = "rotated_text_page"
    _write_text_pdf(OUT / f"{fid}.pdf", ["Rotated challenge line ALPHA"])
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="Rotated challenge line ALPHA",
                lines=["Rotated challenge line ALPHA"],
                words=[
                    {
                        "word_id": "W0",
                        "text": "Rotated",
                        "reading_order": 0,
                        "polygon": _quad(0.2, 0.4, 0.8, 0.5),
                    }
                ],
                expected_layer="native_pdf_text",
                review_status="extracted_with_warnings",
                extra={"expected_rotation": 90, "challenge": "rotated"},
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    # 7 skewed scan (image)
    fid = "skewed_scan_page"
    (OUT / f"{fid}.png").write_bytes(_png_rgb(200, 200, (240, 240, 240)))
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="SKEW SAMPLE",
                lines=["SKEW SAMPLE"],
                words=[
                    {
                        "word_id": "W0",
                        "text": "SKEW",
                        "reading_order": 0,
                        "polygon": _quad(0.2, 0.4, 0.5, 0.5),
                    }
                ],
                expected_layer="fresh_ocr",
                review_status="extracted_with_warnings",
                extra={"challenge": "skew", "deskew_required": True},
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    # 8 image-only no text layer
    fid = "image_only_no_text_layer"
    (OUT / f"{fid}.png").write_bytes(_png_rgb(180, 180, (250, 250, 250)))
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="TYPED SCAN LINE",
                lines=["TYPED SCAN LINE"],
                words=[
                    {
                        "word_id": "W0",
                        "text": "TYPED",
                        "reading_order": 0,
                        "polygon": _quad(0.1, 0.1, 0.4, 0.2),
                    }
                ],
                expected_layer="fresh_ocr",
                review_status="faithful_canonical",
                extra={"ocr_required": True, "native_trustworthy": False},
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    # 9 image with correct hidden OCR — represented as PDF with matching text
    fid = "image_with_correct_hidden_ocr"
    _write_text_pdf(OUT / f"{fid}.pdf", ["HIDDEN OCR CORRECT"])
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="HIDDEN OCR CORRECT",
                lines=["HIDDEN OCR CORRECT"],
                words=[
                    {
                        "word_id": "W0",
                        "text": "HIDDEN",
                        "reading_order": 0,
                        "polygon": _quad(0.1, 0.1, 0.3, 0.2),
                    }
                ],
                expected_layer="embedded_ocr",
                review_status="faithful_canonical",
                extra={"corrupt_embedded": False, "native_trustworthy": True},
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    # 10 corrupt hidden OCR
    fid = "corrupt_hidden_ocr"
    _write_text_pdf(OUT / f"{fid}.pdf", ["Badge ID Go1s"])  # deliberate corrupt reading
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="Badge ID A1234",
                lines=["Badge ID A1234"],
                words=[
                    {
                        "word_id": "W0",
                        "text": "Badge",
                        "reading_order": 0,
                        "polygon": _quad(0.1, 0.1, 0.25, 0.2),
                    },
                    {
                        "word_id": "W1",
                        "text": "ID",
                        "reading_order": 1,
                        "polygon": _quad(0.26, 0.1, 0.35, 0.2),
                    },
                    {
                        "word_id": "W2",
                        "text": "A1234",
                        "reading_order": 2,
                        "polygon": _quad(0.36, 0.1, 0.55, 0.2),
                    },
                ],
                expected_layer="fresh_ocr",
                review_status="unreadable_review_required",
                extra={
                    "corrupt_embedded": True,
                    "must_reject_corrupt": True,
                    "ocr_required": True,
                    "native_trustworthy": False,
                    "embedded_candidate": "Go1s",
                    "visible_expected": "A1234",
                    "critical_fields": [
                        {
                            "field_id": "badge",
                            "field_type": "badge_id",
                            "expected": "A1234",
                            "hypothesized": "Go1s",
                            "uncertain": True,
                            "accepted": False,
                            "review_required": True,
                            "layer_used": "embedded_ocr",
                        }
                    ],
                },
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    # 11 boxed characters
    fid = "boxed_individual_characters"
    _write_text_pdf(OUT / f"{fid}.pdf", ["A B C D"])
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="A B C D",
                lines=["A B C D"],
                words=[
                    {
                        "word_id": f"W{i}",
                        "text": ch,
                        "reading_order": i,
                        "polygon": _quad(0.1 + i * 0.15, 0.4, 0.2 + i * 0.15, 0.5),
                    }
                    for i, ch in enumerate(["A", "B", "C", "D"])
                ],
                expected_layer="native_pdf_text",
                review_status="faithful_canonical",
                extra={"challenge": "boxed_chars"},
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    # 12 mixed print/hand-like
    fid = "mixed_print_handwritten_like"
    _write_text_pdf(OUT / f"{fid}.pdf", ["PRINT LABEL", "handish value xx"])
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="PRINT LABEL\nhandish value xx",
                lines=["PRINT LABEL", "handish value xx"],
                words=[
                    {
                        "word_id": "W0",
                        "text": "PRINT",
                        "reading_order": 0,
                        "polygon": _quad(0.1, 0.1, 0.3, 0.2),
                    }
                ],
                expected_layer="fresh_ocr",
                review_status="ambiguous_with_alternatives",
                extra={"challenge": "mixed_hand"},
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    # 13 diagram grid
    fid = "diagram_grid_labels"
    _write_text_pdf(OUT / f"{fid}.pdf", ["N", "E", "S", "W", "GRID"])
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="N E S W GRID",
                lines=["N E S W GRID"],
                words=[
                    {
                        "word_id": f"W{i}",
                        "text": t,
                        "reading_order": i,
                        "polygon": _quad(0.1 + i * 0.1, 0.1, 0.18 + i * 0.1, 0.18),
                    }
                    for i, t in enumerate(["N", "E", "S", "W", "GRID"])
                ],
                expected_layer="native_pdf_text",
                review_status="unsupported",
                extra={"challenge": "diagram"},
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    # 14 overlapping duplicate hidden text
    fid = "overlapping_duplicate_hidden_text"
    _write_text_pdf(OUT / f"{fid}.pdf", ["DUPLICATE LINE", "DUPLICATE LINE"])
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="DUPLICATE LINE",
                lines=["DUPLICATE LINE"],
                words=[
                    {
                        "word_id": "W0",
                        "text": "DUPLICATE",
                        "reading_order": 0,
                        "polygon": _quad(0.1, 0.1, 0.4, 0.2),
                    }
                ],
                expected_layer="native_pdf_text",
                review_status="extracted_with_warnings",
                extra={"duplicate_text_layer_rate": 1.0, "challenge": "duplicate_layer"},
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    # 15 person name focus
    fid = "person_name_field"
    _write_text_pdf(OUT / f"{fid}.pdf", ["Client: Jordan Lee"])
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="Client: Jordan Lee",
                lines=["Client: Jordan Lee"],
                words=[
                    {
                        "word_id": "W0",
                        "text": "Jordan",
                        "reading_order": 0,
                        "polygon": _quad(0.3, 0.1, 0.5, 0.2),
                    },
                    {
                        "word_id": "W1",
                        "text": "Lee",
                        "reading_order": 1,
                        "polygon": _quad(0.51, 0.1, 0.65, 0.2),
                    },
                ],
                expected_layer="native_pdf_text",
                review_status="faithful_canonical",
                extra={
                    "critical_fields": [
                        {
                            "field_id": "person",
                            "field_type": "person_name",
                            "expected": "Jordan Lee",
                            "hypothesized": "Jordan Lee",
                            "uncertain": False,
                            "accepted": True,
                            "review_required": False,
                            "layer_used": "native_pdf_text",
                        }
                    ]
                },
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    # 16 law firm
    fid = "law_firm_name_field"
    _write_text_pdf(OUT / f"{fid}.pdf", ["North Harbor Legal Group, PLLC"])
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="North Harbor Legal Group, PLLC",
                lines=["North Harbor Legal Group, PLLC"],
                words=[
                    {
                        "word_id": f"W{i}",
                        "text": w,
                        "reading_order": i,
                        "polygon": _quad(0.1 + i * 0.12, 0.1, 0.2 + i * 0.12, 0.2),
                    }
                    for i, w in enumerate(["North", "Harbor", "Legal", "Group,", "PLLC"])
                ],
                expected_layer="native_pdf_text",
                review_status="faithful_canonical",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    # 17 date and identifier
    fid = "date_identifier_fields"
    _write_text_pdf(OUT / f"{fid}.pdf", ["Date 2024-01-15", "ID ID-10042"])
    (OUT / f"{fid}.ground_truth.json").write_text(
        json.dumps(
            _gt(
                fid,
                transcript="Date 2024-01-15\nID ID-10042",
                lines=["Date 2024-01-15", "ID ID-10042"],
                words=[
                    {
                        "word_id": "W0",
                        "text": "2024-01-15",
                        "reading_order": 0,
                        "polygon": _quad(0.2, 0.1, 0.5, 0.2),
                    },
                    {
                        "word_id": "W1",
                        "text": "ID-10042",
                        "reading_order": 1,
                        "polygon": _quad(0.2, 0.25, 0.5, 0.35),
                    },
                ],
                expected_layer="native_pdf_text",
                review_status="faithful_canonical",
                extra={
                    "critical_fields": [
                        {
                            "field_id": "date",
                            "field_type": "date",
                            "expected": "2024-01-15",
                            "hypothesized": "2024-01-15",
                            "uncertain": False,
                            "accepted": True,
                            "review_required": False,
                            "layer_used": "native_pdf_text",
                        },
                        {
                            "field_id": "id",
                            "field_type": "id",
                            "expected": "ID-10042",
                            "hypothesized": "ID-10042",
                            "uncertain": False,
                            "accepted": True,
                            "review_required": False,
                            "layer_used": "native_pdf_text",
                        },
                    ]
                },
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    created.append(fid)

    manifest = {
        "schema_label": "EVALUATION SCHEMA — NOT YET PRODUCTION CONTRACT",
        "fixture_count": len(created),
        "fixtures": created,
        "note": "Synthetic only — no private case names or values",
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Synthetic extraction acceptance fixtures\n\n"
        "Safe committed fixtures for Remediation Part 1.\n"
        "No real client names, case numbers, or private hashes.\n"
        "Rebuild with: `python scripts/extraction_acceptance/build_synthetic_fixtures.py`\n",
        encoding="utf-8",
    )
    # silence unused import
    _ = math
    return created


if __name__ == "__main__":
    ids = build_all()
    print(f"built {len(ids)} fixtures -> {OUT}")

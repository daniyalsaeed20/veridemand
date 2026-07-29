"""Generate deterministic synthetic PDFs for Correction 6 targeted repair.

Fixtures A-J under fixtures/synthetic/ocr/targeted-repair/.
Reviewed synthetic text only - no private content.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "fixtures" / "synthetic" / "ocr" / "targeted-repair"


def _font() -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default()
    except OSError:
        return ImageFont.load_default()


def _base_image(
    *,
    width: int = 612,
    height: int = 792,
    title: str,
    body_lines: list[str],
    header: str | None = None,
    footer: str | None = None,
) -> Image.Image:
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = _font()
    if header:
        draw.text((40, 24), header, fill=(0, 0, 0), font=font)
    draw.text((40, 60), title, fill=(0, 0, 0), font=font)
    y = 100
    for line in body_lines:
        draw.text((40, y), line, fill=(0, 0, 0), font=font)
        y += 22
    if footer:
        draw.text((40, height - 40), footer, fill=(0, 0, 0), font=font)
    return img


def _write_pdf_with_ocr_layer(
    path: Path,
    image: Image.Image,
    ocr_tokens: list[tuple[float, float, str]] | list[tuple[int, int, str]],
    *,
    page_size: tuple[float, float] = letter,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = page_size
    c = canvas.Canvas(str(path), pagesize=page_size)
    c.drawImage(ImageReader(image), 0, 0, width=width, height=height)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica", 9)
    for x, y, text in ocr_tokens:
        c.drawString(x, y, text)
    c.showPage()
    c.save()


def _make_a() -> dict[str, Any]:
    """One wrong word in otherwise correct embedded OCR → targeted repair."""
    body = [
        "Patient name Alice Example",
        "Date of visit 12 March 2024",
        "Clinic reference REF-1001",
        "Notes routine follow up visit",
    ]
    img = _base_image(title="Clinic Visit Summary", body_lines=body)
    # Embedded OCR has one wrong token ("Alices" vs visible "Alice")
    tokens = [
        (40, 720, "Patient"),
        (90, 720, "name"),
        (130, 720, "Alices"),  # defective
        (180, 720, "Example"),
        (40, 698, "Date"),
        (70, 698, "of"),
        (90, 698, "visit"),
        (130, 698, "12"),
        (150, 698, "March"),
        (190, 698, "2024"),
        (40, 676, "Clinic"),
        (80, 676, "reference"),
        (140, 676, "REF-1001"),
        (40, 654, "Notes"),
        (80, 654, "routine"),
        (130, 654, "follow"),
        (170, 654, "up"),
        (190, 654, "visit"),
    ]
    path = OUT_DIR / "A-one-wrong-word.pdf"
    _write_pdf_with_ocr_layer(path, img, tokens)
    return {
        "id": "A",
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "expected_route": "embedded_ocr_targeted_repair",
        "notes": "One wrong embedded word; expect targeted repair",
    }


def _make_b() -> dict[str, Any]:
    """Shifted line geometry → local detection repair."""
    body = [
        "Account holder Jordan Lee",
        "Invoice number INV-4402",
        "Amount due 125.00",
        "Payment status unpaid",
    ]
    img = _base_image(title="Billing Notice", body_lines=body)
    # Tokens for second line are vertically shifted vs visible ink.
    tokens = [
        (40, 720, "Account"),
        (90, 720, "holder"),
        (140, 720, "Jordan"),
        (190, 720, "Lee"),
        (40, 640, "Invoice"),  # shifted down relative to visible line
        (90, 640, "number"),
        (140, 640, "INV-4402"),
        (40, 676, "Amount"),
        (90, 676, "due"),
        (120, 676, "125.00"),
        (40, 654, "Payment"),
        (90, 654, "status"),
        (140, 654, "unpaid"),
    ]
    path = OUT_DIR / "B-shifted-line.pdf"
    _write_pdf_with_ocr_layer(path, img, tokens)
    return {
        "id": "B",
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "expected_route": "embedded_ocr_targeted_repair",
        "expected_method": "local_detection_and_recognition",
        "notes": "Shifted line; local detection if geometry unreliable",
    }


def _make_c() -> dict[str, Any]:
    """Defective header, clean body."""
    body = ["Body line one content here", "Body line two content here", "Body line three content"]
    img = _base_image(
        title="Report Body",
        body_lines=body,
        header="HEADER DEFECT TOKEN",
    )
    tokens = [
        (40, 760, "WRONG"),  # defective header OCR
        (90, 760, "HEADER"),
        (40, 720, "Body"),
        (70, 720, "line"),
        (100, 720, "one"),
        (130, 720, "content"),
        (180, 720, "here"),
        (40, 698, "Body"),
        (70, 698, "line"),
        (100, 698, "two"),
        (130, 698, "content"),
        (180, 698, "here"),
        (40, 676, "Body"),
        (70, 676, "line"),
        (100, 676, "three"),
        (140, 676, "content"),
    ]
    path = OUT_DIR / "C-defective-header.pdf"
    _write_pdf_with_ocr_layer(path, img, tokens)
    return {
        "id": "C",
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "expected_route": "embedded_ocr_targeted_repair",
        "notes": "Header-only repair",
    }


def _make_d() -> dict[str, Any]:
    """Defective footer, clean body."""
    body = ["Primary statement alpha", "Primary statement beta", "Primary statement gamma"]
    img = _base_image(
        title="Footer Case",
        body_lines=body,
        footer="PAGE FOOTER MARK",
    )
    tokens = [
        (40, 720, "Primary"),
        (90, 720, "statement"),
        (150, 720, "alpha"),
        (40, 698, "Primary"),
        (90, 698, "statement"),
        (150, 698, "beta"),
        (40, 676, "Primary"),
        (90, 676, "statement"),
        (150, 676, "gamma"),
        (40, 40, "WRONGFOOT"),  # defective footer
        (110, 40, "MARK"),
    ]
    path = OUT_DIR / "D-defective-footer.pdf"
    _write_pdf_with_ocr_layer(path, img, tokens)
    return {
        "id": "D",
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "expected_route": "embedded_ocr_targeted_repair",
        "notes": "Footer-only repair",
    }


def _make_e() -> dict[str, Any]:
    """Two small distant defective regions."""
    body = [
        "Alpha block remains correct here",
        "Middle section stays verified clean",
        "Omega block remains correct here",
    ]
    img = _base_image(title="Two Region Case", body_lines=body)
    tokens = [
        (40, 720, "BAD1"),
        (80, 720, "block"),
        (120, 720, "remains"),
        (180, 720, "correct"),
        (230, 720, "here"),
        (40, 698, "Middle"),
        (90, 698, "section"),
        (140, 698, "stays"),
        (180, 698, "verified"),
        (240, 698, "clean"),
        (40, 676, "BAD2"),
        (80, 676, "block"),
        (120, 676, "remains"),
        (180, 676, "correct"),
        (230, 676, "here"),
    ]
    path = OUT_DIR / "E-two-distant-regions.pdf"
    _write_pdf_with_ocr_layer(path, img, tokens)
    return {
        "id": "E",
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "expected_route": "embedded_ocr_targeted_repair",
        "expected_region_count": 2,
        "notes": "Two bounded distant regions",
    }


def _make_f() -> dict[str, Any]:
    """Large defective region covering most of the page → full OCR."""
    body = [f"Corrupted line {i} content placeholder" for i in range(1, 16)]
    img = _base_image(title="Widespread Defect", body_lines=body)
    tokens = [(40, 720 - i * 18, f"XXXX{i}") for i in range(20)]
    path = OUT_DIR / "F-large-defective-region.pdf"
    _write_pdf_with_ocr_layer(path, img, tokens)
    return {
        "id": "F",
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "expected_route": "full_visual_ocr",
        "notes": "Large defective coverage → full visual OCR",
    }


def _make_g() -> dict[str, Any]:
    """Many scattered defective words → full OCR."""
    body = [f"Row {i} label value {i * 3}" for i in range(1, 20)]
    img = _base_image(title="Scattered Failures", body_lines=body)
    tokens = []
    y = 720
    for i in range(1, 20):
        tokens.append((40, y, f"BAD{i}"))
        tokens.append((90, y, "label"))
        tokens.append((140, y, f"ZZ{i}"))
        y -= 22
    path = OUT_DIR / "G-scattered-defects.pdf"
    _write_pdf_with_ocr_layer(path, img, tokens)
    return {
        "id": "G",
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "expected_route": "full_visual_ocr",
        "notes": "Many scattered failures → full OCR not hundreds of crops",
    }


def _make_h() -> dict[str, Any]:
    """Clean embedded OCR → verified, no repair."""
    body = [
        "Clean line one verified",
        "Clean line two verified",
        "Clean line three verified",
    ]
    img = _base_image(title="Clean Embedded", body_lines=body)
    tokens = [
        (40, 720, "Clean"),
        (80, 720, "line"),
        (110, 720, "one"),
        (140, 720, "verified"),
        (40, 698, "Clean"),
        (80, 698, "line"),
        (110, 698, "two"),
        (140, 698, "verified"),
        (40, 676, "Clean"),
        (80, 676, "line"),
        (110, 676, "three"),
        (140, 676, "verified"),
    ]
    path = OUT_DIR / "H-clean-embedded.pdf"
    _write_pdf_with_ocr_layer(path, img, tokens)
    return {
        "id": "H",
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "expected_route": "embedded_ocr_verified",
        "notes": "Clean embedded OCR; no repair",
    }


def _make_i() -> dict[str, Any]:
    """Image-only page → full visual OCR."""
    img = _base_image(
        title="Image Only Page",
        body_lines=["Visible printed text without OCR layer"],
    )
    path = OUT_DIR / "I-image-only.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawImage(ImageReader(img), 0, 0, width=letter[0], height=letter[1])
    c.showPage()
    c.save()
    return {
        "id": "I",
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "expected_route": "full_visual_ocr",
        "notes": "Image-only; full visual OCR",
    }


def _make_j() -> dict[str, Any]:
    """Repair crop with handwritten-like strokes → printed provisional, HW pending."""
    img = Image.new("RGB", (612, 792), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = _font()
    draw.text((40, 60), "Handwriting Pending Case", fill=(0, 0, 0), font=font)
    draw.text((40, 100), "Printed label VALUE", fill=(0, 0, 0), font=font)
    # Squiggly "handwritten" strokes in value area.
    for i in range(8):
        x0 = 200 + i * 12
        draw.line((x0, 110 + (i % 3) * 3, x0 + 10, 118 - (i % 2) * 4), fill=(20, 20, 90), width=2)
    tokens = [
        (40, 720, "Printed"),
        (90, 720, "label"),
        (130, 720, "WRONGVAL"),  # defective; repair crop includes HW ink
    ]
    path = OUT_DIR / "J-handwriting-crop.pdf"
    _write_pdf_with_ocr_layer(path, img, tokens)
    return {
        "id": "J",
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "expected_route": "embedded_ocr_targeted_repair",
        "handwriting_assessment": "pending_phase_5",
        "notes": "Printed repair provisional; handwriting pending Phase 5",
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries = [
        _make_a(),
        _make_b(),
        _make_c(),
        _make_d(),
        _make_e(),
        _make_f(),
        _make_g(),
        _make_h(),
        _make_i(),
        _make_j(),
    ]
    manifest = {
        "policy_version": "phase4-targeted-repair-v1",
        "fixtures": entries,
    }
    (OUT_DIR / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "README.md").write_text(
        "# Targeted-repair synthetic fixtures (Correction 6)\n\n"
        "Deterministic reviewed synthetic PDFs A-J. Regenerate with:\n\n"
        "```bash\n"
        "uv run python scripts/generate_targeted_repair_fixtures.py\n"
        "```\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(entries)} fixtures to {OUT_DIR}")


if __name__ == "__main__":
    main()

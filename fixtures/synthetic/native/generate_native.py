"""Generate deterministic, non-sensitive Phase 3 native-PDF fixtures.

Run from the repository root:

    $env:Path = "$env:USERPROFILE\\.local\\bin;" + $env:Path
    uv run python fixtures/synthetic/native/generate_native.py

The generated PDFs are intentionally committed alongside this script so trust-gate
tests can use a small, auditable corpus.  No fixture contains personal, medical,
or case-derived information.
"""

from __future__ import annotations

from pathlib import Path

import reportlab
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    RectangleObject,
)
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

OUT_DIR = Path(__file__).resolve().parent
PAGE_WIDTH, PAGE_HEIGHT = letter
UNICODE_FONT = "SyntheticVera"
UNICODE_BOLD_FONT = "SyntheticVeraBold"
REPORTLAB_FONTS = Path(reportlab.__file__).resolve().parent / "fonts"

pdfmetrics.registerFont(TTFont(UNICODE_FONT, str(REPORTLAB_FONTS / "Vera.ttf")))
pdfmetrics.registerFont(TTFont(UNICODE_BOLD_FONT, str(REPORTLAB_FONTS / "VeraBd.ttf")))


def pdf_canvas(path: Path) -> canvas.Canvas:
    """Create an invariant ReportLab canvas for byte-stable regeneration."""
    return canvas.Canvas(str(path), pagesize=letter, invariant=1, pageCompression=0)


def draw_good_page(pdf: canvas.Canvas, page_number: int = 1) -> None:
    pdf.setTitle("Synthetic native-text fixture")
    pdf.setFont(UNICODE_BOLD_FONT, 18)
    pdf.drawString(72, 730, f"Synthetic Native Text - Page {page_number}")
    pdf.setFont(UNICODE_FONT, 11)
    pdf.drawString(
        72, 700, "This deterministic paragraph contains digits 0123456789 and punctuation: ,.;:!?"
    )
    pdf.drawString(72, 684, "Accented Unicode: café, naïve, résumé, jalapeño, and coöperate.")
    pdf.setFont("Courier", 10)
    pdf.drawString(72, 650, "Code: INV-2026-042 | Status: READY | Amount: 123.45")
    pdf.setFont(UNICODE_BOLD_FONT, 11)
    pdf.drawString(72, 615, "Item")
    pdf.drawString(250, 615, "Count")
    pdf.drawString(380, 615, "Note")
    pdf.setFont(UNICODE_FONT, 10)
    rows = (
        ("Alpha", "12", "plain text"),
        ("Bravo", "34", "table-like layout"),
        ("Café", "56", "Unicode"),
    )
    for index, (item, count, note) in enumerate(rows):
        y = 595 - index * 20
        pdf.drawString(72, y, item)
        pdf.drawRightString(285, y, count)
        pdf.drawString(380, y, note)
    pdf.setFont(UNICODE_FONT, 9)
    pdf.drawString(
        72, 515, "All content is synthetic and contains no private or medical information."
    )


def write_good_single_page(path: Path) -> None:
    pdf = pdf_canvas(path)
    draw_good_page(pdf)
    pdf.save()


def write_good_multipage(path: Path) -> None:
    pdf = pdf_canvas(path)
    for page_number in range(1, 4):
        draw_good_page(pdf, page_number)
        pdf.showPage()
    pdf.save()


def rewrite_page(path: Path, mutate_page: object) -> None:
    reader = PdfReader(path)
    writer = PdfWriter()
    for page in reader.pages:
        mutate_page(page)
        writer.add_page(page)
    with path.open("wb") as handle:
        writer.write(handle)


def write_rotated(path: Path) -> None:
    write_good_single_page(path)

    def rotate(page: object) -> None:
        page.rotate(90)  # type: ignore[attr-defined]

    rewrite_page(path, rotate)


def write_cropbox(path: Path) -> None:
    write_good_single_page(path)

    def crop(page: object) -> None:
        page.cropbox = RectangleObject((36, 48, PAGE_WIDTH - 36, PAGE_HEIGHT - 48))  # type: ignore[attr-defined]

    rewrite_page(path, crop)


def make_page_image(path: Path) -> Path:
    image_path = path.with_suffix(".png")
    image = Image.new("RGB", (612, 792), (245, 248, 252))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 572, 752), outline=(20, 70, 120), width=4)
    draw.text((70, 90), "Synthetic raster page", fill=(10, 30, 60))
    draw.text((70, 125), "Pixels only: no PDF text layer.", fill=(10, 30, 60))
    draw.text((70, 160), "Numbers: 0123456789", fill=(10, 30, 60))
    image.save(image_path, format="PNG", optimize=False)
    return image_path


def write_image_only(path: Path) -> None:
    image_path = make_page_image(path)
    try:
        pdf = pdf_canvas(path)
        pdf.drawImage(str(image_path), 0, 0, width=PAGE_WIDTH, height=PAGE_HEIGHT)
        pdf.save()
    finally:
        image_path.unlink(missing_ok=True)


def write_mixed_native_image(path: Path) -> None:
    image_path = make_page_image(path)
    try:
        pdf = pdf_canvas(path)
        draw_good_page(pdf)
        pdf.showPage()
        pdf.drawImage(str(image_path), 0, 0, width=PAGE_WIDTH, height=PAGE_HEIGHT)
        pdf.save()
    finally:
        image_path.unlink(missing_ok=True)


def to_unicode_cmap(codepoints: list[int]) -> bytes:
    entries = "\n".join(f"<{code:02X}> <{point:04X}>" for code, point in enumerate(codepoints, 1))
    return (
        "/CIDInit /ProcSet findresource begin\n"
        "12 dict begin\nbegincmap\n"
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        "/CMapName /SyntheticUnicode def\n/CMapType 2 def\n"
        "1 begincodespacerange\n<00> <FF>\nendcodespacerange\n"
        f"{len(codepoints)} beginbfchar\n{entries}\nendbfchar\n"
        "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"
    ).encode("ascii")


def write_raw_text_layer(path: Path, codepoints: list[int], content: bytes) -> None:
    """Write a page with an explicit ToUnicode map, including non-printable codepoints."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    cmap = DecodedStreamObject()
    cmap.set_data(to_unicode_cmap(codepoints))
    cmap_ref = writer._add_object(cmap)  # pypdf's public API has no ToUnicode helper.
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
            NameObject("/ToUnicode"): cmap_ref,
        }
    )
    resources = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
        }
    )
    page[NameObject("/Resources")] = resources
    stream = DecodedStreamObject()
    stream.set_data(content)
    page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as handle:
        writer.write(handle)


def write_replacement_characters(path: Path) -> None:
    write_raw_text_layer(
        path,
        [ord("A"), 0xFFFD, ord("B"), 0xFFFD, ord("C")],
        b"BT /F1 16 Tf 72 720 Td <0102030405> Tj ET",
    )


def write_private_use(path: Path) -> None:
    write_raw_text_layer(
        path,
        [ord("P"), 0xE001, ord("R"), 0xE002, ord("I")],
        b"BT /F1 16 Tf 72 720 Td <0102030405> Tj ET",
    )


def write_control_characters(path: Path) -> None:
    write_raw_text_layer(
        path,
        [ord("A"), 0x0001, ord("B"), 0x0002, ord("C")],
        b"BT /F1 16 Tf 72 720 Td <0102030405> Tj ET",
    )


def write_duplicate_text(path: Path) -> None:
    pdf = pdf_canvas(path)
    pdf.setFont("Helvetica", 14)
    for _ in range(50):
        pdf.drawString(72, 720, "DUPLICATED OVERLAPPING NATIVE TEXT 12345")
    pdf.save()


def write_out_of_bounds(path: Path) -> None:
    pdf = pdf_canvas(path)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(-400, -200, "OUTSIDE LOWER LEFT")
    pdf.drawString(PAGE_WIDTH + 100, PAGE_HEIGHT + 100, "OUTSIDE UPPER RIGHT")
    pdf.drawString(72, 720, "Visible anchor text")
    pdf.save()


def write_cid_tokens(path: Path) -> None:
    pdf = pdf_canvas(path)
    pdf.setFont("Courier", 12)
    pdf.drawString(72, 720, "(cid:123) (cid:456) (cid:789) literal extraction tokens")
    pdf.save()


def write_symbol_noise(path: Path) -> None:
    pdf = pdf_canvas(path)
    pdf.setFont("Courier", 14)
    for index in range(12):
        pdf.drawString(72, 720 - index * 28, "!@#$%^&*() []{} <> /\\ | ~` += _-")
    pdf.save()


def write_corrupt_geometry(path: Path) -> None:
    # Zero text-scale and negative horizontal scale approximate malformed character geometry.
    write_raw_text_layer(
        path,
        [ord(char) for char in "GEOMETRY"],
        b"BT /F1 16 Tf 0 0 0 0 150 500 Tm <0102030405060708> Tj ET\n"
        b"BT /F1 16 Tf -1 0 0 1 400 500 Tm <0102030405060708> Tj ET",
    )


def write_noncharacter_layer(path: Path) -> None:
    # U+FFFE and U+FFFF are Unicode noncharacters.
    write_raw_text_layer(
        path,
        [ord("N"), 0xFFFE, ord("O"), 0xFFFF, ord("N")],
        b"BT /F1 16 Tf 72 720 Td <0102030405> Tj ET",
    )


def write_parser_error_page(path: Path) -> None:
    """Single page whose content stream is intentionally unreadable to pdfminer."""

    writer = PdfWriter()
    page = writer.add_blank_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    resources = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): DictionaryObject(
                        {
                            NameObject("/Type"): NameObject("/Font"),
                            NameObject("/Subtype"): NameObject("/Type1"),
                            NameObject("/BaseFont"): NameObject("/Helvetica"),
                        }
                    )
                }
            )
        }
    )
    page[NameObject("/Resources")] = resources
    stream = DecodedStreamObject()
    # Truncated/illegal operators commonly trip pdfminer while parsing page content.
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (broken\x00stream BI /W 1 /H 1 /BPC 8 ID <<")
    page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as handle:
        writer.write(handle)


def write_good_with_one_parser_error(path: Path) -> None:
    """Three pages: good, parser-error, good — tests page-level containment."""

    good = OUT_DIR / "_tmp_good_page.pdf"
    bad = OUT_DIR / "_tmp_bad_page.pdf"
    write_good_single_page(good)
    write_parser_error_page(bad)
    writer = PdfWriter()
    writer.add_page(PdfReader(str(good)).pages[0])
    writer.add_page(PdfReader(str(bad)).pages[0])
    write_good_single_page(good)
    writer.add_page(PdfReader(str(good)).pages[0])
    with path.open("wb") as handle:
        writer.write(handle)
    good.unlink(missing_ok=True)
    bad.unlink(missing_ok=True)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    generators = {
        "good-native-single-page.pdf": write_good_single_page,
        "good-native-multipage.pdf": write_good_multipage,
        "good-native-rotated.pdf": write_rotated,
        "good-native-cropbox.pdf": write_cropbox,
        "image-only.pdf": write_image_only,
        "mixed-native-image.pdf": write_mixed_native_image,
        "replacement-character-layer.pdf": write_replacement_characters,
        "private-use-layer.pdf": write_private_use,
        "control-character-layer.pdf": write_control_characters,
        "duplicate-text-layer.pdf": write_duplicate_text,
        "out-of-bounds-text-layer.pdf": write_out_of_bounds,
        "cid-token-layer.pdf": write_cid_tokens,
        "symbol-noise-layer.pdf": write_symbol_noise,
        "corrupt-geometry-layer.pdf": write_corrupt_geometry,
        "noncharacter-layer.pdf": write_noncharacter_layer,
        "parser-error-page.pdf": write_parser_error_page,
        "good-with-one-parser-error.pdf": write_good_with_one_parser_error,
    }
    for name, writer_fn in generators.items():
        writer_fn(OUT_DIR / name)
    print(f"Wrote {len(generators)} synthetic native fixtures to {OUT_DIR}")


if __name__ == "__main__":
    main()

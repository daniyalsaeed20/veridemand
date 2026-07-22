"""Split one corpus page into a temporary single-page PDF."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, NameObject


def _copy_box(writer_page: object, source_page: object, box_name: str) -> None:
    box = source_page.get(NameObject(box_name))  # type: ignore[attr-defined]
    if box is None:
        return
    writer_page[NameObject(box_name)] = ArrayObject(box)  # type: ignore[index]


def split_page_to_pdf(
    source_pdf: Path,
    page_number: int,
    destination: Path,
) -> Path:
    """Write a one-page PDF for ``page_number`` (1-based).

    Preserves MediaBox, CropBox, and /Rotate from the source page. Does not
    modify the original fixture.
    """

    if page_number < 1:
        raise ValueError(f"page_number must be >= 1, got {page_number}")

    reader = PdfReader(str(source_pdf))
    if page_number > len(reader.pages):
        raise ValueError(f"page_number {page_number} exceeds PDF page count {len(reader.pages)}")

    source_page = reader.pages[page_number - 1]
    writer = PdfWriter()
    writer.add_page(source_page)
    out_page = writer.pages[0]

    # pypdf add_page usually clones boxes; re-assert CropBox/MediaBox/Rotate explicitly.
    _copy_box(out_page, source_page, "/MediaBox")
    if source_page.get(NameObject("/CropBox")) is not None:
        _copy_box(out_page, source_page, "/CropBox")
    rotate = source_page.get(NameObject("/Rotate"))
    if rotate is not None:
        out_page[NameObject("/Rotate")] = rotate

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        writer.write(handle)
    return destination


def page_rotation(source_pdf: Path, page_number: int) -> int:
    reader = PdfReader(str(source_pdf))
    page = reader.pages[page_number - 1]
    rotate = page.get(NameObject("/Rotate"))
    if rotate is None:
        return 0
    return int(rotate) % 360


def page_cropbox(source_pdf: Path, page_number: int) -> tuple[float, float, float, float] | None:
    reader = PdfReader(str(source_pdf))
    page = reader.pages[page_number - 1]
    crop = page.get(NameObject("/CropBox"))
    if crop is None:
        return None
    values = [float(v) for v in crop]
    if len(values) != 4:
        return None
    return values[0], values[1], values[2], values[3]

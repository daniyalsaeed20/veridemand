"""Build canonical viewing PDFs from raster images (JPG/PNG/TIFF)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps
from pypdf import PdfWriter


def images_to_canonical_pdf(source: Path, output_pdf: Path) -> int:
    """Wrap one or more image frames into a PDF viewing copy.

    Preserves EXIF orientation via ImageOps.exif_transpose. Returns page count.
    """
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    frames: list[Image.Image] = []
    with Image.open(source) as img:
        n_frames = int(getattr(img, "n_frames", 1) or 1)
        for index in range(n_frames):
            img.seek(index)
            frame = ImageOps.exif_transpose(img.copy())
            if frame.mode not in {"RGB", "L"}:
                frame = frame.convert("RGB")
            frames.append(frame)

    if not frames:
        raise ValueError("image has no frames")

    tmp = output_pdf.with_suffix(".tmp.pdf")
    try:
        first, rest = frames[0], frames[1:]
        if rest:
            first.save(tmp, format="PDF", resolution=72.0, save_all=True, append_images=rest)
        else:
            first.save(tmp, format="PDF", resolution=72.0)
        if output_pdf.exists():
            output_pdf.unlink()
        tmp.replace(output_pdf)
    finally:
        for frame in frames:
            frame.close()
        if tmp.exists():
            tmp.unlink(missing_ok=True)

    return len(frames)


def write_blank_pdf(output_pdf: Path, *, width: float = 612, height: float = 792) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=height)
    with output_pdf.open("wb") as fh:
        writer.write(fh)


def write_rotated_pdf(output_pdf: Path, *, rotation: int = 90) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    page.rotate(rotation)
    with output_pdf.open("wb") as fh:
        writer.write(fh)


def write_cropbox_pdf(
    output_pdf: Path,
    *,
    media_width: float = 612,
    media_height: float = 792,
    crop: tuple[float, float, float, float] = (50.0, 50.0, 500.0, 700.0),
) -> None:
    """Synthetic PDF whose CropBox differs from MediaBox."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=media_width, height=media_height)
    llx, lly, urx, ury = crop
    page.cropbox.lower_left = (llx, lly)
    page.cropbox.upper_right = (urx, ury)
    with output_pdf.open("wb") as fh:
        writer.write(fh)

"""Page thumbnail generation via pypdfium2."""

from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from app.core.logging import get_logger

logger = get_logger(__name__)


class ThumbnailError(Exception):
    """Failed to render a thumbnail for a PDF page."""


def create_thumbnails(
    canonical_pdf: Path,
    thumbnails_dir: Path,
    *,
    max_width: int = 240,
    scale: float = 1.0,
) -> list[Path]:
    """Render PNG thumbnails for each page. Returns ordered paths (1-based filenames)."""
    thumbnails_dir.mkdir(parents=True, exist_ok=True)
    # Clear prior thumbs for this document
    for old in thumbnails_dir.glob("page_*.png"):
        old.unlink(missing_ok=True)

    paths: list[Path] = []
    try:
        pdf = pdfium.PdfDocument(str(canonical_pdf))
    except Exception as exc:  # noqa: BLE001
        raise ThumbnailError("Could not open canonical PDF for thumbnails.") from exc

    try:
        page_count = len(pdf)
        for index in range(page_count):
            page = pdf[index]
            try:
                # Bitmap at modest scale; then downscale to max_width
                bitmap = page.render(scale=scale)
                pil = bitmap.to_pil()
                if pil.width > max_width:
                    ratio = max_width / float(pil.width)
                    new_size = (max_width, max(1, int(pil.height * ratio)))
                    pil = pil.resize(new_size, Image.Resampling.LANCZOS)
                out = thumbnails_dir / f"page_{index + 1}.png"
                pil.save(out, format="PNG")
                paths.append(out)
            finally:
                page.close()
    finally:
        pdf.close()

    if not paths:
        raise ThumbnailError("Canonical PDF has no pages for thumbnails.")
    return paths


def count_pdf_pages(canonical_pdf: Path) -> int:
    pdf = pdfium.PdfDocument(str(canonical_pdf))
    try:
        return len(pdf)
    finally:
        pdf.close()

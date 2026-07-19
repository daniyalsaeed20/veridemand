"""Page thumbnail generation via the process-wide PDFium runtime (B-01)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.core.logging import get_logger
from app.services.documents import pdfium_runtime

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
    for old in thumbnails_dir.glob("page_*.png"):
        old.unlink(missing_ok=True)

    try:
        rendered = pdfium_runtime.render_all_pages(canonical_pdf, scale=scale)
    except Exception as exc:  # noqa: BLE001
        raise ThumbnailError("Could not open canonical PDF for thumbnails.") from exc

    if not rendered:
        raise ThumbnailError("Canonical PDF has no pages for thumbnails.")

    paths: list[Path] = []
    # Resize/save outside the PDFium critical section (already released).
    for item in rendered:
        original = item.image
        working = original
        resized: Image.Image | None = None
        try:
            if original.width > max_width:
                ratio = max_width / float(original.width)
                new_size = (max_width, max(1, int(original.height * ratio)))
                resized = original.resize(new_size, Image.Resampling.LANCZOS)
                working = resized
            out = thumbnails_dir / f"page_{item.page_index + 1}.png"
            working.save(out, format="PNG")
            paths.append(out)
        finally:
            if resized is not None:
                resized.close()
            original.close()

    return paths


def count_pdf_pages(canonical_pdf: Path) -> int:
    try:
        return pdfium_runtime.count_pages(canonical_pdf)
    except Exception as exc:  # noqa: BLE001
        raise ThumbnailError("Could not open canonical PDF for page count.") from exc

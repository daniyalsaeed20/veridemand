"""Create committed synthetic OCR fixtures for Phase 4.3 render policy tests."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "synthetic" / "ocr"


def _full_page_scan(*, width: int = 850, height: int = 1100) -> Path:
    """MediaBox points equal image pixels (72 DPI identity scan)."""

    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((40, 40, width - 40, height - 40), outline=(0, 0, 0), width=2)
    for y in range(80, height - 80, 28):
        draw.line((60, y, width - 60, y), fill=(180, 180, 180), width=1)
        draw.text((70, y - 18), f"FORM LINE {y // 28:02d}", fill=(0, 0, 0))
    path = OUT / "full-page-scan-identity.pdf"
    # Page size in points == pixel size → 1 pt per px at 72 DPI.
    c = canvas.Canvas(str(path), pagesize=(width, height))
    c.drawImage(ImageReader(img), 0, 0, width=width, height=height)
    c.showPage()
    c.save()
    return path


def _dense_ruled_form() -> Path:
    path = OUT / "dense-ruled-form.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    c.setFont("Helvetica", 10)
    c.drawString(72, height - 54, "Dense ruled form (synthetic)")
    y = height - 90
    while y > 72:
        c.line(72, y, width - 72, y)
        c.line(72, y, 72, y - 18)
        c.line(width / 2, y, width / 2, y - 18)
        c.line(width - 72, y, width - 72, y - 18)
        y -= 18
    c.save()
    return path


def _large_grid() -> Path:
    path = OUT / "large-grid-page.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    step = 24
    x = 36
    while x < width - 36:
        c.line(x, 36, x, height - 36)
        x += step
    y = 36
    while y < height - 36:
        c.line(36, y, width - 36, y)
        y += step
    c.setFont("Helvetica", 9)
    c.drawString(40, height - 28, "Large grid page (synthetic)")
    c.save()
    return path


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    created = [_full_page_scan(), _dense_ruled_form(), _large_grid()]
    for item in created:
        print(item.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

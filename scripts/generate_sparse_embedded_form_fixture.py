"""Generate a two-page scanned-form PDF with a sparse hidden OCR layer.

The visible scan is a dense ruled form with checkboxes and image-only ink.
The embedded text layer covers only a small subset of visible labels so
Route B can enter embedded verification but coverage must fail and fall
back to full visual OCR (Correction 1).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "synthetic" / "ocr" / "sparse-embedded-form-2page.pdf"


def _form_image(*, page: int, width: int = 850, height: int = 1100) -> Image.Image:
    img = Image.new("RGB", (width, height), (248, 248, 245))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default()
    except OSError:
        font = None

    draw.rectangle((30, 30, width - 30, height - 30), outline=(20, 20, 20), width=3)
    title = f"SYNTHETIC POLICE-STYLE FORM PAGE {page}"
    draw.text((50, 48), title, fill=(0, 0, 0), font=font)

    y = 100
    labels = [
        "INCIDENT NUMBER",
        "DATE OF REPORT",
        "REPORTING OFFICER",
        "LOCATION OF INCIDENT",
        "COMPLAINANT NAME",
        "COMPLAINANT ADDRESS",
        "WITNESS NAME",
        "VEHICLE DESCRIPTION",
        "NARRATIVE SUMMARY",
        "PROPERTY DAMAGE",
        "INJURIES REPORTED",
        "FOLLOW UP REQUIRED",
    ]
    for idx, label in enumerate(labels):
        draw.line((50, y, width - 50, y), fill=(160, 160, 160), width=1)
        draw.text((55, y - 18), label, fill=(0, 0, 0), font=font)
        # Checkbox marks (image-only).
        box = (width - 90, y - 22, width - 70, y - 2)
        draw.rectangle(box, outline=(0, 0, 0), width=2)
        if idx % 3 == 0:
            draw.line((box[0] + 2, box[1] + 2, box[2] - 2, box[3] - 2), fill=(0, 0, 0), width=2)
            draw.line((box[0] + 2, box[3] - 2, box[2] - 2, box[1] + 2), fill=(0, 0, 0), width=2)
        # Image-only "handwritten" strokes in the value area (not in OCR layer).
        hx0, hy0 = 280, y - 16
        draw.line((hx0, hy0 + 8, hx0 + 90, hy0 + 4), fill=(30, 30, 120), width=2)
        draw.arc((hx0 + 100, hy0, hx0 + 140, hy0 + 18), 200, 340, fill=(30, 30, 120), width=2)
        y += 36

    # Extra ruled grid in lower half.
    for gy in range(y, height - 60, 22):
        draw.line((50, gy, width - 50, gy), fill=(200, 200, 200), width=1)
        draw.rectangle((60, gy - 14, 78, gy - 2), outline=(80, 80, 80), width=1)

    # Dense body paragraph as image-only text.
    body = (
        "Image-only narrative block that must not be authoritative from the sparse "
        "embedded OCR layer. Checkbox rows and handwritten strokes remain pending Phase 5."
    )
    draw.text((55, height - 90), body[:70], fill=(40, 40, 40), font=font)
    draw.text((55, height - 72), body[70:], fill=(40, 40, 40), font=font)
    return img


def _draw_sparse_ocr_layer(c: canvas.Canvas, *, page: int, width: float, height: float) -> None:
    """Hidden/background text covering only a few labels near the top."""

    c.setFillColorRGB(1, 1, 1)  # white — effectively invisible on scan
    c.setFont("Helvetica", 8)
    # Sparse coverage: only three short tokens near the top-left.
    sparse = [
        (72, height - 70, f"FORM{page}"),
        (72, height - 100, "INCIDENT"),
        (72, height - 130, "DATE"),
        (72, height - 160, "OFFICER"),
        (72, height - 190, "LOCATION"),
        (200, height - 100, "NUMBER"),
        (200, height - 130, "REPORT"),
        (200, height - 160, "NAME"),
        (200, height - 190, "PLACE"),
        (320, height - 100, "FIELD"),
        (320, height - 130, "VALUE"),
        (320, height - 160, "ENTRY"),
        (320, height - 190, "CODE"),
    ]
    for x, y, text in sparse:
        c.drawString(x, y, text)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    width, height = letter
    c = canvas.Canvas(str(OUT), pagesize=letter)
    for page in (1, 2):
        img = _form_image(page=page)
        # Fit letter page.
        c.drawImage(ImageReader(img), 0, 0, width=width, height=height)
        _draw_sparse_ocr_layer(c, page=page, width=width, height=height)
        c.showPage()
    c.save()
    print(OUT.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

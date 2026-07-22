from __future__ import annotations

import io
import json
import math
import os
import random
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Any

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Text, Highlight, Link, FreeText
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = Path(
    os.environ.get("VERIDEMAND_SMOKE_OUT", str(_REPO_ROOT / "fixtures" / "synthetic" / "smoke"))
)
WORK_DIR = OUT_DIR / "_veridemand_fixture_work"
WORK_DIR.mkdir(parents=True, exist_ok=True)
BASE_PDF = WORK_DIR / "veridemand_synthetic_base.pdf"
FINAL_PDF = OUT_DIR / "VeriDemand_Synthetic_PDF_Regression_Corpus_v1.0.pdf"
MANIFEST = OUT_DIR / "VeriDemand_Synthetic_PDF_Regression_Manifest_v1.0.json"

random.seed(20260723)

PAGE_W, PAGE_H = A4
MARGIN = 42


def _first_existing(*candidates: str) -> str | None:
    for path in candidates:
        if path and Path(path).is_file():
            return path
    return None


# Fonts are used internally only; they are embedded/subset into the generated PDF.
# Prefer Linux package paths; fall back to common Windows locations when regenerating.
FONT_REG = _first_existing(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    r"C:\Windows\Fonts\DejaVuSans.ttf",
    r"C:\Windows\Fonts\arial.ttf",
)
FONT_BOLD = _first_existing(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    r"C:\Windows\Fonts\DejaVuSans-Bold.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
)
FONT_HEBREW = _first_existing(
    "/usr/share/fonts/truetype/noto/NotoSansHebrew-Regular.ttf",
    FONT_REG or "",
)
FONT_ARABIC = _first_existing(
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    FONT_REG or "",
)
FONT_COMIC = _first_existing(
    "/usr/share/fonts/opentype/comic-neue/ComicNeue-Regular.otf",
    r"C:\Windows\Fonts\comic.ttf",
    FONT_REG or "",
)

if not FONT_REG or not FONT_BOLD:
    raise SystemExit(
        "Missing DejaVu/Arial fonts required to regenerate the smoke corpus. "
        "Install DejaVu Sans or set fonts manually before running this script."
    )

pdfmetrics.registerFont(TTFont("VD-Regular", FONT_REG))
pdfmetrics.registerFont(TTFont("VD-Bold", FONT_BOLD))
if FONT_HEBREW:
    pdfmetrics.registerFont(TTFont("VD-Hebrew", FONT_HEBREW))
if FONT_ARABIC:
    pdfmetrics.registerFont(TTFont("VD-Arabic", FONT_ARABIC))
try:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
except Exception:
    pass
try:
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))
except Exception:
    pass


@dataclass
class TestCase:
    test_id: str
    title: str
    category: str
    expected_source_mode: str
    expected_decision: str
    expected_reason_codes: list[str]
    expected_native_text: bool | None
    expected_viewer: str
    notes: str
    page_size: tuple[float, float] = A4
    postprocess: dict[str, Any] | None = None
    phase_expectation: str = "current_phase_expected"
    acceptable_outcomes: list[dict[str, Any]] | None = None


CASES: list[TestCase] = []
BUILDERS: list[Callable[[canvas.Canvas, TestCase], None]] = []


def add_case(case: TestCase):
    def deco(fn: Callable[[canvas.Canvas, TestCase], None]):
        CASES.append(case)
        BUILDERS.append(fn)
        return fn

    return deco


def header(c: canvas.Canvas, case: TestCase, *, raster: bool = False):
    w, h = case.page_size
    c.setFillColor(colors.HexColor("#16324F"))
    c.rect(0, h - 54, w, 54, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("VD-Bold", 13)
    c.drawString(MARGIN, h - 33, f"{case.test_id} - {case.title}")
    c.setFont("VD-Regular", 8.5)
    c.drawRightString(w - MARGIN, h - 33, f"Expected: {case.expected_source_mode}")
    c.setFillColor(colors.HexColor("#EAF2F8"))
    c.rect(MARGIN, h - 88, w - 2 * MARGIN, 24, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#16324F"))
    c.setFont("VD-Regular", 8)
    c.drawString(MARGIN + 8, h - 80, case.notes[:130])


def footer(c: canvas.Canvas, case: TestCase):
    w, _ = case.page_size
    c.setStrokeColor(colors.HexColor("#B8C5D1"))
    c.line(MARGIN, 28, w - MARGIN, 28)
    c.setFillColor(colors.HexColor("#5A6A78"))
    c.setFont("VD-Regular", 7.5)
    c.drawString(MARGIN, 16, "Synthetic regression fixture - no private or real patient data")
    c.drawRightString(w - MARGIN, 16, case.test_id)


def body_intro(c: canvas.Canvas, case: TestCase, y: float | None = None):
    _, h = case.page_size
    y = y or h - 120
    c.setFillColor(colors.black)
    c.setFont("VD-Regular", 10)
    c.drawString(
        MARGIN,
        y,
        "Golden reference: The visible page should be compared with extracted native text and geometry.",
    )


def draw_wrapped(
    c: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    font="VD-Regular",
    size=9.5,
    leading=13,
):
    c.setFont(font, size)
    words = text.split()
    line = ""
    cy = y
    for word in words:
        candidate = (line + " " + word).strip()
        if pdfmetrics.stringWidth(candidate, font, size) > width and line:
            c.drawString(x, cy, line)
            cy -= leading
            line = word
        else:
            line = candidate
    if line:
        c.drawString(x, cy, line)
        cy -= leading
    return cy


def make_page_image(
    title: str,
    lines: list[str],
    *,
    size=(1240, 1754),
    low_res=False,
    bilevel=False,
    skew=0.0,
    perspective=False,
    handwriting=False,
    wrong_color=False,
) -> Image.Image:
    if low_res:
        size = (620, 877)
    bg = (244, 246, 249) if not wrong_color else (250, 243, 229)
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    scale = size[0] / 1240
    font_path = FONT_COMIC if handwriting else FONT_REG
    bold_path = FONT_BOLD
    f_title = ImageFont.truetype(bold_path, max(18, int(34 * scale)))
    f_body = ImageFont.truetype(font_path, max(12, int(24 * scale)))
    f_small = ImageFont.truetype(FONT_REG, max(10, int(18 * scale)))
    d.rectangle((0, 0, size[0], int(120 * scale)), fill=(22, 50, 79))
    d.text((int(55 * scale), int(35 * scale)), title, font=f_title, fill="white")
    y = int(165 * scale)
    for i, line in enumerate(lines):
        if i in (2, 6):
            d.line(
                (
                    int(70 * scale),
                    y - int(8 * scale),
                    size[0] - int(70 * scale),
                    y - int(8 * scale),
                ),
                fill=(120, 130, 140),
                width=max(1, int(2 * scale)),
            )
        d.text((int(75 * scale), y), line, font=f_body, fill=(25, 30, 35))
        y += int(48 * scale)
    d.text(
        (int(75 * scale), size[1] - int(80 * scale)),
        "Synthetic regression fixture - no private data",
        font=f_small,
        fill=(80, 90, 100),
    )
    if handwriting:
        # Add varied handwritten-like notes.
        for j in range(6):
            yy = int((720 + j * 85) * scale)
            d.text(
                (int((120 + (j % 2) * 35) * scale), yy),
                f"Note {j + 1}: follow-up value {100 + j}.25",
                font=f_body,
                fill=(20, 55, 110),
            )
    if bilevel:
        img = img.convert("L").point(lambda p: 255 if p > 160 else 0, mode="1").convert("RGB")
    if skew:
        img = img.rotate(skew, expand=True, fillcolor=(220, 220, 220))
        canvas_img = Image.new("RGB", size, (210, 210, 210))
        img.thumbnail(size)
        canvas_img.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2))
        img = canvas_img
    if perspective:
        # Simulate a photographed page with a mild perspective warp.
        src = img
        w, h = src.size
        coeffs = _find_coeffs(
            [(0, 0), (w, 0), (w, h), (0, h)], [(55, 30), (w - 75, 0), (w - 20, h - 40), (20, h)]
        )
        img = src.transform(
            (w, h),
            Image.Transform.PERSPECTIVE,
            coeffs,
            Image.Resampling.BICUBIC,
            fillcolor=(185, 185, 185),
        )
    return img


def _find_coeffs(pa, pb):
    # Solve perspective coefficients using numpy-free Gaussian elimination.
    import numpy as np

    matrix = []
    for p1, p2 in zip(pa, pb):
        matrix.append([p1[0], p1[1], 1, 0, 0, 0, -p2[0] * p1[0], -p2[0] * p1[1]])
        matrix.append([0, 0, 0, p1[0], p1[1], 1, -p2[1] * p1[0], -p2[1] * p1[1]])
    A = np.matrix(matrix, dtype=float)
    B = np.array(pb).reshape(8)
    res = np.dot(np.linalg.inv(A.T * A) * A.T, B)
    return np.array(res).reshape(8)


def place_full_page_image(c: canvas.Canvas, img: Image.Image, case: TestCase, *, jpeg=False):
    suffix = ".jpg" if jpeg else ".png"
    path = WORK_DIR / f"{case.test_id}{suffix}"
    if jpeg:
        img.save(path, "JPEG", quality=86)
    else:
        img.save(path, "PNG")
    w, h = case.page_size
    c.drawImage(str(path), 0, 0, width=w, height=h, preserveAspectRatio=False, mask="auto")


def invisible_text(
    c: canvas.Canvas, lines: list[str], *, x=72, y=700, font="VD-Regular", size=10, leading=16
):
    t = c.beginText()
    t.setTextOrigin(x, y)
    t.setFont(font, size)
    t.setLeading(leading)
    t.setTextRenderMode(3)
    for line in lines:
        t.textLine(line)
    c.drawText(t)


def dense_lines(prefix="Synthetic record", count=18):
    return [
        f"{prefix} line {i + 1:02d}: date 2026-07-{(i % 28) + 1:02d}, amount {(i + 1) * 37.25:,.2f}, code VD-{1000 + i}."
        for i in range(count)
    ]


# --- Test cases ---


@add_case(
    TestCase(
        "T01",
        "Clean digital baseline",
        "native_text",
        "native_authority",
        "accepted",
        [],
        True,
        "normal",
        "Healthy machine-generated text with ordinary geometry.",
    )
)
def t01(c, case):
    header(c, case)
    body_intro(c, case)
    y = case.page_size[1] - 150
    c.setFont("VD-Bold", 16)
    c.drawString(MARGIN, y, "Synthetic Account Summary")
    y -= 34
    for label, value in [
        ("Reference", "VD-2026-0001"),
        ("Service date", "2026-07-23"),
        ("Balance", "$1,234.56"),
        ("Status", "Open"),
    ]:
        c.setFont("VD-Bold", 10)
        c.drawString(MARGIN, y, label + ":")
        c.setFont("VD-Regular", 10)
        c.drawString(MARGIN + 110, y, value)
        y -= 22
    draw_wrapped(
        c,
        "This clean page is expected to use its native text layer. Coordinates, Unicode and token structure are ordinary and deterministic.",
        MARGIN,
        y - 10,
        PAGE_W - 2 * MARGIN,
    )
    footer(c, case)


@add_case(
    TestCase(
        "T02",
        "Clean dense ruled table",
        "tables",
        "native_authority",
        "accepted",
        [],
        True,
        "normal",
        "Dense table with clear ruling, dates, currency and totals.",
    )
)
def t02(c, case):
    header(c, case)
    x0, y0 = MARGIN, case.page_size[1] - 140
    cols = [x0, x0 + 70, x0 + 220, x0 + 330, x0 + 430, case.page_size[0] - MARGIN]
    rows = 14
    rh = 30
    c.setFont("VD-Bold", 8)
    headers = ["Line", "Description", "Date", "Qty", "Amount"]
    for i, h in enumerate(headers):
        c.drawString(cols[i] + 4, y0 - 20, h)
    c.setStrokeColor(colors.grey)
    for r in range(rows + 1):
        c.line(x0, y0 - r * rh, cols[-1], y0 - r * rh)
    for x in cols:
        c.line(x, y0, x, y0 - rows * rh)
    c.setFont("VD-Regular", 7.5)
    for r in range(1, rows):
        vals = [
            str(r),
            f"Synthetic service {r}",
            f"2026-07-{r:02d}",
            str((r % 4) + 1),
            f"${r * 48.75:,.2f}",
        ]
        for i, v in enumerate(vals):
            c.drawString(cols[i] + 4, y0 - r * rh - 19, v)
    footer(c, case)


@add_case(
    TestCase(
        "T03",
        "Non-embedded Base14 font",
        "fonts",
        "native_authority",
        "accepted",
        [],
        True,
        "normal",
        "Standard Helvetica text without an embedded TrueType font.",
    )
)
def t03(c, case):
    header(c, case)
    c.setFont("Helvetica", 14)
    c.drawString(MARGIN, case.page_size[1] - 150, "Base14 Helvetica: ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    c.setFont("Helvetica", 10)
    for i, line in enumerate(dense_lines("Base14 line", 12)):
        c.drawString(MARGIN, case.page_size[1] - 190 - i * 24, line)
    footer(c, case)


@add_case(
    TestCase(
        "T04",
        "Embedded TrueType subset font",
        "fonts",
        "native_authority",
        "accepted",
        [],
        True,
        "normal",
        "Embedded DejaVu Sans subset with Unicode punctuation and accented letters.",
    )
)
def t04(c, case):
    header(c, case)
    c.setFont("VD-Regular", 13)
    c.drawString(
        MARGIN,
        case.page_size[1] - 150,
        "Embedded text: cafe, naive, resume, Sao Paulo, £123.45, EUR 99.00",
    )
    for i, line in enumerate(dense_lines("Embedded-font line", 12)):
        c.drawString(MARGIN, case.page_size[1] - 190 - i * 24, line)
    footer(c, case)


@add_case(
    TestCase(
        "T05",
        "Exact duplicate native text layer",
        "duplicate_layers",
        "visual_authority",
        "rejected",
        ["excessive_duplicates", "native_text_rejected"],
        False,
        "single-copy or slightly bold",
        "The same native text is painted twice at identical coordinates.",
    )
)
def t05(c, case):
    header(c, case)
    lines = dense_lines("Exact duplicate", 18)
    for _ in range(2):
        c.setFont("VD-Regular", 10)
        for i, line in enumerate(lines):
            c.drawString(MARGIN, case.page_size[1] - 135 - i * 30, line)
    footer(c, case)


@add_case(
    TestCase(
        "T06",
        "Cross-font near-overprint duplicate",
        "duplicate_layers",
        "visual_authority",
        "rejected",
        ["excessive_near_overprint_duplicates", "native_text_rejected"],
        False,
        "visually near-single-copy",
        "A second cross-font text layer is offset by about one point.",
        acceptable_outcomes=[
            {
                "decision": "accepted",
                "source_mode": "native_authority",
                "require_no_interleaved_duplicates": True,
            },
            {
                "decision": "rejected",
                "source_mode": "visual_authority",
                "require_reason_codes": ["excessive_near_overprint_duplicates"],
            },
        ],
    )
)
def t06(c, case):
    header(c, case)
    lines = dense_lines("Near-overprint account", 18)
    c.setFont("VD-Regular", 10)
    for i, line in enumerate(lines):
        c.drawString(MARGIN, case.page_size[1] - 135 - i * 30, line)
    c.setFont("Helvetica", 9.6)
    for i, line in enumerate(lines):
        c.drawString(MARGIN + 0.8, case.page_size[1] - 134 - i * 30, line)
    footer(c, case)


@add_case(
    TestCase(
        "T07",
        "Partial duplicate header and footer",
        "duplicate_layers",
        "visual_authority",
        "rejected",
        ["excessive_near_overprint_duplicates"],
        False,
        "body clean, header/footer overprinted",
        "Only regional text bands are duplicated; global duplication is diluted.",
        acceptable_outcomes=[
            {
                "decision": "accepted",
                "source_mode": "native_authority",
                "require_no_interleaved_duplicates": True,
                "forbidden_substrings": [
                    "SSYYNNTTHHEETTIICC",
                    "BILLINGHEADER",
                    "BILILLININGG",
                ],
            },
            {
                "decision": "rejected",
                "source_mode": "visual_authority",
                "require_reason_codes": ["excessive_near_overprint_duplicates"],
            },
        ],
    )
)
def t07(c, case):
    header(c, case)
    c.setFont("VD-Regular", 10)
    body = dense_lines("Clean body", 12)
    for i, line in enumerate(body):
        c.drawString(MARGIN, case.page_size[1] - 210 - i * 32, line)
    dup = ["SYNTHETIC BILLING HEADER - ACCOUNT VD-7788", "Prepared 2026-07-23 - Page 1 of 1"]
    for font, dx, dy in [("VD-Regular", 0, 0), ("Helvetica", 0.7, 1.1)]:
        c.setFont(font, 11 if font == "VD-Regular" else 10.5)
        c.drawString(MARGIN, case.page_size[1] - 130 + dy, dup[0])
        c.drawString(MARGIN, 58 + dy, dup[1])
    footer(c, case)


@add_case(
    TestCase(
        "T08",
        "Raster drop shadow with clean native text",
        "duplicate_controls",
        "native_authority",
        "accepted",
        [],
        True,
        "normal shadow",
        "False-positive control: shadow is raster; native characters occur only once.",
    )
)
def t08(c, case):
    header(c, case)
    img = Image.new("RGBA", (900, 180), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT_BOLD, 54)
    d.text((24, 34), "DROP SHADOW CONTROL", font=f, fill=(0, 0, 0, 100), stroke_width=0)
    img = img.filter(ImageFilter.GaussianBlur(3))
    p = WORK_DIR / "T08-shadow.png"
    img.save(p)
    c.drawImage(str(p), MARGIN, case.page_size[1] - 270, width=500, height=100, mask="auto")
    c.setFont("VD-Bold", 28)
    c.drawString(MARGIN + 10, case.page_size[1] - 220, "DROP SHADOW CONTROL")
    c.setFont("VD-Regular", 10)
    for i, line in enumerate(dense_lines("Control text", 10)):
        c.drawString(MARGIN, case.page_size[1] - 320 - i * 28, line)
    footer(c, case)


@add_case(
    TestCase(
        "T09",
        "Clean bold typography control",
        "duplicate_controls",
        "native_authority",
        "accepted",
        [],
        True,
        "normal",
        "Bold face appears once and must not be mistaken for duplicate overprint.",
    )
)
def t09(c, case):
    header(c, case)
    c.setFont("VD-Bold", 22)
    c.drawString(MARGIN, case.page_size[1] - 150, "BOLD TEXT IS NOT A DUPLICATE LAYER")
    c.setFont("VD-Bold", 11)
    for i, line in enumerate(dense_lines("Bold control", 14)):
        c.drawString(MARGIN, case.page_size[1] - 200 - i * 30, line)
    footer(c, case)


SCAN_LINES = [
    "Synthetic Medical Statement",
    "Patient: SAMPLE PERSON",
    "Account: VD-100200",
    "Service Date: 2026-07-01",
    "Procedure: Evaluation and treatment",
    "Billed: $1,450.00",
    "Paid: $500.00",
    "Balance: $950.00",
    "This page is entirely synthetic.",
]


@add_case(
    TestCase(
        "T10",
        "Full-page image-only scan",
        "scanned_pages",
        "image_authority",
        "rejected",
        ["image_dominant_page", "native_text_absent"],
        False,
        "renders as readable scan",
        "No native text layer exists.",
    )
)
def t10(c, case):
    img = make_page_image("T10 - IMAGE-ONLY SCAN", SCAN_LINES)
    place_full_page_image(c, img, case)


@add_case(
    TestCase(
        "T11",
        "Full-page scan with accurate invisible OCR",
        "hidden_ocr",
        "visual_authority",
        "rejected",
        ["image_dominant_page"],
        False,
        "scan looks normal",
        "Invisible native OCR agrees with the image but Phase 3 should be conservative.",
    )
)
def t11(c, case):
    img = make_page_image("T11 - SCAN + ACCURATE HIDDEN OCR", SCAN_LINES)
    place_full_page_image(c, img, case)
    invisible_text(c, SCAN_LINES, x=50, y=700, size=11, leading=28)


@add_case(
    TestCase(
        "T12",
        "Full-page scan with plausible wrong OCR",
        "hidden_ocr",
        "visual_authority",
        "rejected",
        ["image_dominant_page", "visual_mismatch_expected"],
        False,
        "scan shows correct values",
        "Invisible OCR changes dates and money while remaining plausible.",
    )
)
def t12(c, case):
    img = make_page_image("T12 - SCAN + WRONG HIDDEN OCR", SCAN_LINES)
    place_full_page_image(c, img, case)
    wrong = [
        "Synthetic Medical Statement",
        "Patient: SAMPLE PERSON",
        "Account: VD-100299",
        "Service Date: 2026-07-07",
        "Procedure: Evaluation and treatment",
        "Billed: $1,850.00",
        "Paid: $50.00",
        "Balance: $1,800.00",
    ]
    invisible_text(c, wrong, x=50, y=700, size=11, leading=28)


@add_case(
    TestCase(
        "T13",
        "Full-page scan with shifted OCR coordinates",
        "hidden_ocr",
        "visual_authority",
        "rejected",
        ["image_dominant_page", "visual_geometry_mismatch_expected"],
        False,
        "scan looks normal",
        "Invisible OCR text is displaced from the visual lines.",
    )
)
def t13(c, case):
    img = make_page_image("T13 - SHIFTED OCR COORDINATES", SCAN_LINES)
    place_full_page_image(c, img, case)
    invisible_text(c, SCAN_LINES, x=170, y=580, size=11, leading=28)


@add_case(
    TestCase(
        "T14",
        "Mixed native body and scan region",
        "mixed_content",
        "native_authority",
        "accepted",
        [],
        True,
        "native body plus image block",
        "An image region exists but does not dominate the page.",
    )
)
def t14(c, case):
    header(c, case)
    c.setFont("VD-Regular", 10)
    for i, line in enumerate(dense_lines("Digital paragraph", 12)):
        c.drawString(MARGIN, case.page_size[1] - 135 - i * 25, line)
    img = make_page_image(
        "SCANNED ATTACHMENT", ["Image block only", "No hidden OCR in this region"], size=(620, 450)
    )
    p = WORK_DIR / "T14.png"
    img.save(p)
    c.drawImage(str(p), MARGIN, 70, width=300, height=220)
    c.setFont("VD-Regular", 9)
    c.drawString(360, 250, "Native caption beside the scan region.")
    footer(c, case)


@add_case(
    TestCase(
        "T15",
        "Image-dominant page with small native caption",
        "image_dominance",
        "visual_authority",
        "rejected",
        ["image_dominant_page"],
        False,
        "large image with caption",
        "A full-page image dominates even though a small native caption exists.",
    )
)
def t15(c, case):
    img = make_page_image("T15 - IMAGE-DOMINANT PAGE", SCAN_LINES)
    place_full_page_image(c, img, case)
    c.setFont("VD-Regular", 7)
    c.setFillColor(colors.black)
    c.drawString(15, 12, "Small native caption: should not override image dominance.")


@add_case(
    TestCase(
        "T16",
        "Sparse native text on mostly blank page",
        "sparse_text",
        "visual_authority",
        "rejected",
        ["native_text_too_sparse", "native_text_absent"],
        False,
        "mostly blank",
        "Only one small native token exists; no header/footer chrome. Identified via manifest.",
    )
)
def t16(c, case):
    # Intentionally no native header/footer — chrome would defeat sparsity
    # (native_min_characters). Page identity lives in the manifest only.
    # Optional non-native vector mark (paths only; no Tj/TJ text operators).
    w, h = case.page_size
    c.setStrokeColor(colors.HexColor("#B8C5D1"))
    c.setLineWidth(0.75)
    c.rect(MARGIN, h - 40, 36, 18, stroke=1, fill=0)
    c.setFillColor(colors.black)
    c.setFont("VD-Regular", 8)
    c.drawString(PAGE_W / 2, PAGE_H / 2, "VD-1")


@add_case(
    TestCase(
        "T17",
        "Off-page hidden native text",
        "geometry",
        "visual_authority",
        "rejected",
        ["native_geometry_out_of_bounds"],
        False,
        "visible page looks clean",
        "Many native strings are placed beyond the left page boundary.",
    )
)
def t17(c, case):
    header(c, case)
    c.setFont("VD-Regular", 11)
    c.drawString(MARGIN, PAGE_H - 150, "Visible reference text is ordinary.")
    t = c.beginText()
    t.setTextOrigin(-260, PAGE_H - 200)
    t.setFont("VD-Regular", 10)
    t.setLeading(18)
    t.setTextRenderMode(3)
    for line in dense_lines("OFFPAGE", 20):
        t.textLine(line)
    c.drawText(t)
    footer(c, case)


@add_case(
    TestCase(
        "T18",
        "White-on-white hidden native text",
        "visibility",
        "visual_authority",
        "rejected",
        ["visual_agreement_required"],
        False,
        "visible page has little text",
        "White native text is extractable but invisible on a white background. "
        "Phase 4 visibility probe must downgrade it.",
        phase_expectation="current_phase_expected",
    )
)
def t18(c, case):
    header(c, case)
    c.setFillColor(colors.black)
    c.setFont("VD-Regular", 11)
    c.drawString(MARGIN, PAGE_H - 145, "Only this sentence is visibly printed.")
    c.setFillColor(colors.white)
    c.setFont("VD-Regular", 11)
    for i, line in enumerate(dense_lines("WHITE HIDDEN", 20)):
        c.drawString(MARGIN, PAGE_H - 190 - i * 24, line)
    c.setFillColor(colors.black)
    footer(c, case)


@add_case(
    TestCase(
        "T19",
        "Invisible text rendering mode",
        "visibility",
        "visual_authority",
        "rejected",
        ["visual_agreement_required"],
        False,
        "visible page has a reference box",
        "Render mode 3 creates extractable text with no visible glyphs. "
        "Phase 4 visibility probe must downgrade it.",
        phase_expectation="current_phase_expected",
    )
)
def t19(c, case):
    header(c, case)
    c.setStrokeColor(colors.darkblue)
    c.rect(MARGIN, 220, PAGE_W - 2 * MARGIN, 300, stroke=1, fill=0)
    c.setFont("VD-Regular", 11)
    c.drawString(MARGIN, 540, "The box below appears empty, but invisible native text occupies it.")
    invisible_text(
        c, dense_lines("INVISIBLE RENDER MODE", 18), x=MARGIN + 15, y=490, size=10, leading=15
    )
    footer(c, case)


@add_case(
    TestCase(
        "T20",
        "CropBox hides live native text",
        "page_boxes",
        "native_authority",
        "accepted",
        ["cropped_content_present"],
        True,
        "cropped edge hidden",
        "Text outside the CropBox remains in the content stream.",
        postprocess={"cropbox": [55, 55, 540, 770]},
    )
)
def t20(c, case):
    header(c, case)
    c.setFillColor(colors.HexColor("#F6D5D5"))
    c.rect(0, 0, PAGE_W, 55, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont("VD-Bold", 10)
    c.drawString(10, 20, "CROPPED-AWAY LIVE TEXT: VD-SECRET-2026")
    c.setFont("VD-Regular", 11)
    for i, line in enumerate(dense_lines("Visible cropbox content", 15)):
        c.drawString(MARGIN, PAGE_H - 145 - i * 32, line)
    footer(c, case)


@add_case(
    TestCase(
        "T21",
        "Page rotation metadata 90 degrees",
        "rotation",
        "native_authority",
        "accepted",
        [],
        True,
        "rotated portrait page",
        "Page /Rotate is set to 90 while text remains geometrically valid.",
        postprocess={"rotate": 90},
    )
)
def t21(c, case):
    header(c, case)
    c.setFont("VD-Bold", 24)
    c.drawCentredString(PAGE_W / 2, PAGE_H / 2, "ROTATION 90 DEGREES")
    c.setFont("VD-Regular", 11)
    for i, line in enumerate(dense_lines("Rotated page line", 10)):
        c.drawString(MARGIN, PAGE_H - 155 - i * 30, line)
    footer(c, case)


@add_case(
    TestCase(
        "T22",
        "Page rotation metadata 180 degrees",
        "rotation",
        "native_authority",
        "accepted",
        [],
        True,
        "upside-down page",
        "Page /Rotate is set to 180. Soft-pass until rotation tokenisation/"
        "extraction-order handling is hardened (same class as T21).",
        postprocess={"rotate": 180},
        phase_expectation="not_yet_implemented",
    )
)
def t22(c, case):
    header(c, case)
    c.setFont("VD-Bold", 24)
    c.drawCentredString(PAGE_W / 2, PAGE_H / 2, "ROTATION 180 DEGREES")
    c.setFont("VD-Regular", 11)
    for i, line in enumerate(dense_lines("Upside-down line", 10)):
        c.drawString(MARGIN, PAGE_H - 155 - i * 30, line)
    footer(c, case)


@add_case(
    TestCase(
        "T23",
        "Small square page size",
        "page_sizes",
        "native_authority",
        "accepted",
        [],
        True,
        "300 x 300 point page",
        "One document contains a much smaller page than the surrounding pages.",
        page_size=(300, 300),
    )
)
def t23(c, case):
    # Compact chrome only — A4 header/footer strings overflow a 300×300 page.
    w, h = case.page_size
    c.setFillColor(colors.HexColor("#16324F"))
    c.rect(0, h - 28, w, 28, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("VD-Bold", 9)
    c.drawString(10, h - 18, "T23 small page")
    c.setFillColor(colors.black)
    c.setFont("VD-Regular", 8)
    for i in range(7):
        c.drawString(12, 200 - i * 20, f"Line {i + 1}: VD-{2300 + i}")
    c.setFont("VD-Regular", 7)
    c.setFillColor(colors.HexColor("#5A6A78"))
    c.drawString(10, 10, "synthetic")


@add_case(
    TestCase(
        "T24",
        "Landscape page",
        "page_sizes",
        "native_authority",
        "accepted",
        [],
        True,
        "landscape page",
        "Landscape orientation and wide coordinate mapping.",
        page_size=landscape(A4),
    )
)
def t24(c, case):
    header(c, case)
    w, h = case.page_size
    c.setFont("VD-Bold", 24)
    c.drawCentredString(w / 2, h - 160, "LANDSCAPE COORDINATE TEST")
    c.setFont("VD-Regular", 10)
    for i in range(16):
        c.drawString(
            MARGIN,
            h - 205 - i * 24,
            f"Wide line {i + 1:02d} - x-span test - amount {i * 71.50:,.2f}",
        )
    footer(c, case)


@add_case(
    TestCase(
        "T25",
        "Oversized page",
        "page_sizes",
        "native_authority",
        "accepted",
        [],
        True,
        "1200 x 900 point page",
        "Large engineering-style page tests fit-page, fit-width and coordinate scaling.",
        page_size=(1200, 900),
    )
)
def t25(c, case):
    header(c, case)
    w, h = case.page_size
    c.setFont("VD-Bold", 30)
    c.drawString(70, h - 150, "OVERSIZED PAGE - 1200 x 900 pt")
    c.setStrokeColor(colors.HexColor("#567"))
    c.grid([70 + i * 100 for i in range(11)], [100 + i * 70 for i in range(10)])
    c.setFont("VD-Regular", 12)
    for i in range(12):
        c.drawString(
            80,
            h - 210 - i * 40,
            f"Grid reference {i + 1} - coordinate marker x={80 + i * 60}, y={h - 210 - i * 40}",
        )
    footer(c, case)


@add_case(
    TestCase(
        "T26",
        "Non-zero MediaBox origin",
        "page_boxes",
        "native_authority",
        "accepted",
        [],
        True,
        "content shifted within unusual origin",
        "MediaBox and CropBox start at negative coordinates. Soft-pass until "
        "non-zero page-origin mapping is hardened for Phase 3.",
        postprocess={"mediabox": [-50, -40, 545, 802]},
        phase_expectation="not_yet_implemented",
    )
)
def t26(c, case):
    header(c, case)
    c.setFont("VD-Bold", 18)
    c.drawString(MARGIN, PAGE_H - 150, "NON-ZERO PAGE ORIGIN")
    c.setFont("VD-Regular", 10)
    for i, line in enumerate(dense_lines("Origin test", 15)):
        c.drawString(MARGIN, PAGE_H - 190 - i * 30, line)
    footer(c, case)


@add_case(
    TestCase(
        "T27",
        "Two-column reading order",
        "reading_order",
        "native_authority",
        "accepted",
        ["reading_order_provisional"],
        True,
        "two visible columns",
        "Native words are valid but semantic order may be ambiguous.",
    )
)
def t27(c, case):
    header(c, case)
    colw = (PAGE_W - 2 * MARGIN - 24) / 2
    c.setFont("VD-Bold", 12)
    c.drawString(MARGIN, PAGE_H - 140, "COLUMN A")
    c.drawString(MARGIN + colw + 24, PAGE_H - 140, "COLUMN B")
    c.setFont("VD-Regular", 8.5)
    for i in range(22):
        c.drawString(
            MARGIN,
            PAGE_H - 170 - i * 26,
            f"A{i + 1:02d}: Left column sentence and value {100 + i}.",
        )
        c.drawString(
            MARGIN + colw + 24,
            PAGE_H - 170 - i * 26,
            f"B{i + 1:02d}: Right column sentence and value {500 + i}.",
        )
    footer(c, case)


@add_case(
    TestCase(
        "T28",
        "Three-column reading order",
        "reading_order",
        "native_authority",
        "accepted",
        ["reading_order_provisional"],
        True,
        "three narrow columns",
        "Narrow columns challenge sequence reconstruction.",
    )
)
def t28(c, case):
    header(c, case)
    gap = 14
    colw = (PAGE_W - 2 * MARGIN - 2 * gap) / 3
    c.setFont("VD-Regular", 7.2)
    for col in range(3):
        x = MARGIN + col * (colw + gap)
        c.setFont("VD-Bold", 9)
        c.drawString(x, PAGE_H - 140, f"COLUMN {col + 1}")
        c.setFont("VD-Regular", 7.2)
        for i in range(28):
            c.drawString(
                x, PAGE_H - 165 - i * 21, f"C{col + 1}-{i + 1:02d} value {col * 100 + i:03d}"
            )
    footer(c, case)


@add_case(
    TestCase(
        "T29",
        "Content-stream order differs from visual order",
        "reading_order",
        "native_authority",
        "accepted",
        ["reading_order_provisional"],
        True,
        "left column appears first visually",
        "Right column is painted first in the content stream.",
    )
)
def t29(c, case):
    header(c, case)
    colw = (PAGE_W - 2 * MARGIN - 24) / 2
    # Paint right column first intentionally.
    c.setFont("VD-Regular", 8.5)
    for i in range(20):
        c.drawString(
            MARGIN + colw + 24,
            PAGE_H - 165 - i * 28,
            f"RIGHT-{i + 1:02d}: painted first, read second visually",
        )
    for i in range(20):
        c.drawString(
            MARGIN, PAGE_H - 165 - i * 28, f"LEFT-{i + 1:02d}: painted second, read first visually"
        )
    c.setFont("VD-Bold", 11)
    c.drawString(MARGIN, PAGE_H - 140, "VISUAL LEFT")
    c.drawString(MARGIN + colw + 24, PAGE_H - 140, "VISUAL RIGHT")
    footer(c, case)


@add_case(
    TestCase(
        "T30",
        "Ruled table with merged headers",
        "tables",
        "native_authority",
        "accepted",
        ["structure_provisional"],
        True,
        "visible merged table headers",
        "Merged headings and grouped numeric columns.",
    )
)
def t30(c, case):
    header(c, case)
    x0 = MARGIN
    y0 = PAGE_H - 135
    widths = [75, 160, 85, 85, 85]
    xs = [x0]
    for w in widths:
        xs.append(xs[-1] + w)
    c.setStrokeColor(colors.black)
    # merged group header
    c.rect(xs[0], y0 - 34, widths[0] + widths[1], 34, stroke=1, fill=0)
    c.rect(xs[2], y0 - 34, widths[2] + widths[3] + widths[4], 34, stroke=1, fill=0)
    c.setFont("VD-Bold", 9)
    c.drawCentredString((xs[0] + xs[2]) / 2, y0 - 22, "SERVICE")
    c.drawCentredString((xs[2] + xs[5]) / 2, y0 - 22, "FINANCIALS")
    rh = 28
    rows = 15
    for r in range(rows + 1):
        c.line(x0, y0 - 34 - r * rh, xs[-1], y0 - 34 - r * rh)
    for x in xs:
        c.line(x, y0 - 34, x, y0 - 34 - rows * rh)
    c.setFont("VD-Regular", 7.2)
    for r in range(rows):
        vals = [
            f"{r + 1}",
            f"Procedure {r + 1}",
            f"${100 + r * 7}",
            f"${20 + r * 2}",
            f"${80 + r * 5}",
        ]
        for i, v in enumerate(vals):
            c.drawString(xs[i] + 3, y0 - 34 - (r + 1) * rh + 9, v)
    footer(c, case)


@add_case(
    TestCase(
        "T31",
        "Borderless table",
        "tables",
        "native_authority",
        "accepted",
        ["structure_provisional"],
        True,
        "aligned values without ruling",
        "Whitespace and alignment carry the table structure.",
    )
)
def t31(c, case):
    header(c, case)
    xs = [MARGIN, MARGIN + 75, MARGIN + 260, MARGIN + 385]
    c.setFont("VD-Bold", 9)
    for x, h in zip(xs, ["ID", "Description", "Date", "Amount"]):
        c.drawString(x, PAGE_H - 145, h)
    c.setFont("VD-Regular", 8)
    for r in range(22):
        vals = [
            f"{r + 1:03d}",
            f"Borderless service description {r + 1}",
            f"2026-07-{(r % 28) + 1:02d}",
            f"${(r + 1) * 61.35:,.2f}",
        ]
        for x, v in zip(xs, vals):
            c.drawString(x, PAGE_H - 175 - r * 26, v)
    footer(c, case)


@add_case(
    TestCase(
        "T32",
        "Table with multi-line cells",
        "tables",
        "native_authority",
        "accepted",
        ["structure_provisional"],
        True,
        "multi-line cells and wrapped values",
        "Cell content spans multiple visual lines.",
    )
)
def t32(c, case):
    header(c, case)
    x0 = MARGIN
    y = PAGE_H - 140
    widths = [55, 255, 100, 100]
    rh = 64
    xs = [x0]
    for w in widths:
        xs.append(xs[-1] + w)
    c.setStrokeColor(colors.grey)
    for r in range(9):
        c.rect(x0, y - (r + 1) * rh, sum(widths), rh, stroke=1, fill=0)
        for x in xs[1:-1]:
            c.line(x, y - r * rh, x, y - (r + 1) * rh)
        c.setFont("VD-Regular", 7.5)
        c.drawString(xs[0] + 4, y - r * rh - 20, str(r + 1))
        c.drawString(
            xs[1] + 4, y - r * rh - 18, f"Multi-line description for synthetic row {r + 1}"
        )
        c.drawString(
            xs[1] + 4, y - r * rh - 35, "Second line contains details and a reference code."
        )
        c.drawString(xs[2] + 4, y - r * rh - 22, f"2026-07-{r + 1:02d}")
        c.drawString(xs[3] + 4, y - r * rh - 22, f"${(r + 1) * 88.10:,.2f}")
    footer(c, case)


@add_case(
    TestCase(
        "T33",
        "Repeated header and footer content",
        "repeated_content",
        "native_authority",
        "accepted",
        ["repeated_header_footer"],
        True,
        "repeated page furniture",
        "Tests recognition of boilerplate versus body text.",
    )
)
def t33(c, case):
    header(c, case)
    c.setFont("VD-Bold", 11)
    for y in [PAGE_H - 125, 100]:
        c.drawString(MARGIN, y, "REPEATED SYNTHETIC ORGANISATION HEADER - CONFIDENTIAL")
    c.setFont("VD-Regular", 9)
    for i, line in enumerate(dense_lines("Main body unique", 17)):
        c.drawString(MARGIN, PAGE_H - 175 - i * 30, line)
    footer(c, case)


@add_case(
    TestCase(
        "T34",
        "Ligatures and kerning",
        "unicode",
        "native_authority",
        "accepted",
        [],
        True,
        "ligature glyphs visible",
        "Contains fi/fl ligatures and ordinary repeated letters.",
    )
)
def t34(c, case):
    header(c, case)
    c.setFont("VD-Regular", 18)
    lines = [
        "office profile efficient affine flower fluff",
        "Ligatures: ﬁ ﬁnancial ﬂ flow ﬃ (if supported)",
        "Legitimate repeats: letter bookkeeper committee 100.00",
    ]
    for i, line in enumerate(lines):
        c.drawString(MARGIN, PAGE_H - 160 - i * 55, line)
    c.setFont("VD-Regular", 10)
    for i, line in enumerate(dense_lines("Ligature context", 12)):
        c.drawString(MARGIN, PAGE_H - 350 - i * 28, line)
    footer(c, case)


@add_case(
    TestCase(
        "T35",
        "Unicode NFC and NFD combining marks",
        "unicode",
        "native_authority",
        "accepted",
        [],
        True,
        "accented text should look equivalent",
        "Visually similar composed and decomposed sequences.",
    )
)
def t35(c, case):
    header(c, case)
    c.setFont("VD-Regular", 18)
    nfc = "NFC: café naïve résumé Ångström"
    nfd = "NFD: cafe\u0301 nai\u0308ve re\u0301sume\u0301 A\u030angstro\u0308m"
    c.drawString(MARGIN, PAGE_H - 165, nfc)
    c.drawString(MARGIN, PAGE_H - 225, nfd)
    c.setFont("VD-Regular", 10)
    for i, line in enumerate(dense_lines("Unicode normalisation", 12)):
        c.drawString(MARGIN, PAGE_H - 300 - i * 28, line)
    footer(c, case)


@add_case(
    TestCase(
        "T36",
        "Hebrew right-to-left text with numbers",
        "rtl",
        "native_authority",
        "accepted",
        ["reading_order_provisional"],
        True,
        "Hebrew text and Latin numbers",
        "BiDi order, punctuation and numeric fields are mixed.",
    )
)
def t36(c, case):
    header(c, case)
    c.setFont("VD-Hebrew", 18)
    heb = "בדיקת מסמך סינתטי מספר 12345 תאריך 23/07/2026 סכום 950.00"
    c.drawRightString(PAGE_W - MARGIN, PAGE_H - 170, heb)
    c.setFont("VD-Regular", 10)
    c.drawString(
        MARGIN,
        PAGE_H - 230,
        "Logical/native order may differ from visual RTL order; Unicode must remain valid.",
    )
    footer(c, case)


@add_case(
    TestCase(
        "T37",
        "Arabic Unicode with numbers",
        "rtl",
        "native_authority",
        "accepted",
        ["reading_order_provisional"],
        True,
        "Arabic code points with numeric fields",
        "Exercises Arabic Unicode and directionality; shaping varies by renderer.",
    )
)
def t37(c, case):
    header(c, case)
    c.setFont("VD-Arabic", 18)
    arab = "اختبار مستند اصطناعي رقم 12345 تاريخ 23/07/2026 مبلغ 950.00"
    c.drawRightString(PAGE_W - MARGIN, PAGE_H - 170, arab)
    c.setFont("VD-Regular", 10)
    c.drawString(
        MARGIN,
        PAGE_H - 230,
        "This page tests Unicode validity and directionality rather than language understanding.",
    )
    footer(c, case)


@add_case(
    TestCase(
        "T38",
        "Vertical CJK text",
        "vertical_text",
        "native_authority",
        "accepted",
        ["reading_order_provisional"],
        True,
        "vertical character columns",
        "Characters are individually positioned from top to bottom.",
    )
)
def t38(c, case):
    header(c, case)
    chars = "縦書き文書試験東京一二三"
    c.setFont("STSong-Light", 20)
    for col in range(4):
        x = PAGE_W - 120 - col * 70
        for i, ch in enumerate(chars):
            c.drawString(x, PAGE_H - 150 - i * 32, ch)
    c.setFont("VD-Regular", 10)
    c.drawString(
        MARGIN, 120, "Vertical layout should not be mistaken for random single-character noise."
    )
    footer(c, case)


@add_case(
    TestCase(
        "T39",
        "CID-backed CJK native text",
        "unicode",
        "native_authority",
        "accepted",
        [],
        True,
        "Chinese and Japanese text",
        "CID font mapping and full-width digits.",
    )
)
def t39(c, case):
    header(c, case)
    c.setFont("STSong-Light", 19)
    for i, line in enumerate(
        [
            "東京 テスト １２３",
            "合成文書検査 金額 ９５０．００",
            "患者情報ではなく完全なテストデータです",
        ]
    ):
        c.drawString(MARGIN, PAGE_H - 165 - i * 55, line)
    c.setFont("VD-Regular", 10)
    c.drawString(MARGIN, PAGE_H - 350, "Expected: valid Unicode mapping and positive geometry.")
    footer(c, case)


@add_case(
    TestCase(
        "T40",
        "Emoji and supplementary-plane symbols",
        "unicode",
        "native_authority",
        "accepted",
        ["unsupported_glyphs_possible"],
        True,
        "some glyphs may fall back",
        "Tests characters outside the Basic Multilingual Plane.",
    )
)
def t40(c, case):
    header(c, case)
    c.setFont("VD-Regular", 17)
    c.drawString(MARGIN, PAGE_H - 165, "Supplementary symbols: 😀 🚑 🧾 ⚖ ☑ ✨ 𝟙 𝟚 𝟛")
    c.setFont("VD-Regular", 10)
    for i, line in enumerate(dense_lines("Emoji context", 12)):
        c.drawString(MARGIN, PAGE_H - 220 - i * 28, line)
    footer(c, case)


@add_case(
    TestCase(
        "T41",
        "Private-use and unassigned hidden characters",
        "unicode_noise",
        "visual_authority",
        "rejected",
        ["private_use_unicode", "unassigned_unicode"],
        False,
        "visible page remains ordinary",
        "Hidden text contains private-use and unassigned code points.",
    )
)
def t41(c, case):
    header(c, case)
    c.setFont("VD-Regular", 11)
    c.drawString(MARGIN, PAGE_H - 150, "Visible sentence: all values on this line are ordinary.")
    hidden = ["PRIVATE " + ("\ue000" * 30) + " UNASSIGNED " + ("\u0378" * 30) for _ in range(10)]
    invisible_text(c, hidden, x=MARGIN, y=PAGE_H - 210, font="VD-Regular", size=10, leading=22)
    footer(c, case)


@add_case(
    TestCase(
        "T42",
        "Replacement-character noise",
        "unicode_noise",
        "visual_authority",
        "rejected",
        ["replacement_character_ratio"],
        False,
        "replacement glyphs visible",
        "A high ratio of U+FFFD replacement characters.",
    )
)
def t42(c, case):
    header(c, case)
    c.setFont("VD-Regular", 12)
    noisy = "VALID " + ("�" * 18) + " TOKEN " + ("�" * 18) + " 2026"
    for i in range(18):
        c.drawString(MARGIN, PAGE_H - 145 - i * 30, noisy)
    footer(c, case)


@add_case(
    TestCase(
        "T43",
        "Symbol-only and Dingbats noise",
        "token_noise",
        "visual_authority",
        "rejected",
        ["symbol_only_word_ratio"],
        False,
        "symbol grid",
        "Large symbol-only regions should not be trusted as prose.",
    )
)
def t43(c, case):
    # ZapfDingbats often remaps to Latin letters under extraction (generator defect:
    # produced "nnnn…" rows). Emit ASCII punctuation-only tokens so
    # high_symbol_only_word_ratio fires, without AABB-identical runs.
    header(c, case)
    c.setFont("VD-Regular", 14)
    alphabet = "#$%&*+/=@?!~^|"
    for r in range(22):
        row = "".join(alphabet[(r + i) % len(alphabet)] for i in range(28))
        c.drawString(MARGIN, PAGE_H - 145 - r * 26, row)
    footer(c, case)


@add_case(
    TestCase(
        "T44",
        "Excessive single-character tokens",
        "token_noise",
        "visual_authority",
        "rejected",
        ["single_character_word_ratio"],
        False,
        "spaced character grid",
        "Characters are separated into hundreds of single-token words.",
    )
)
def t44(c, case):
    header(c, case)
    c.setFont("VD-Regular", 10)
    alphabet = "A B C D E F G H I J K L M N O P Q R S T 1 2 3 4 5 6 7 8 9"
    for i in range(22):
        c.drawString(MARGIN, PAGE_H - 145 - i * 27, alphabet)
    footer(c, case)


@add_case(
    TestCase(
        "T45",
        "Superscript and subscript positioning",
        "geometry",
        "native_authority",
        "accepted",
        [],
        True,
        "formula-like text",
        "Small vertically displaced glyphs should remain attached logically.",
    )
)
def t45(c, case):
    header(c, case)
    c.setFont("VD-Regular", 20)
    x = MARGIN
    y = PAGE_H - 170
    c.drawString(x, y, "H")
    c.setFont("VD-Regular", 11)
    c.drawString(x + 15, y - 6, "2")
    c.setFont("VD-Regular", 20)
    c.drawString(x + 24, y, "O + x")
    c.setFont("VD-Regular", 11)
    c.drawString(x + 78, y + 10, "2")
    c.setFont("VD-Regular", 20)
    c.drawString(x + 88, y, " = 125.50")
    c.setFont("VD-Regular", 10)
    for i, line in enumerate(dense_lines("Superscript context", 12)):
        c.drawString(MARGIN, PAGE_H - 240 - i * 28, line)
    footer(c, case)


@add_case(
    TestCase(
        "T46",
        "Extreme character spacing and kerning",
        "geometry",
        "native_authority",
        "accepted",
        ["tokenisation_provisional"],
        True,
        "widely spaced and tightly spaced text",
        "Tests word grouping thresholds without invalid geometry.",
    )
)
def t46(c, case):
    header(c, case)
    t = c.beginText()
    t.setTextOrigin(MARGIN, PAGE_H - 170)
    t.setFont("VD-Regular", 16)
    t.setCharSpace(6)
    t.textLine("WIDE CHARACTER SPACING 12345")
    t.setCharSpace(-1.2)
    t.textLine("TIGHTCHARACTERSPACING-ABCDE-67890")
    c.drawText(t)
    c.setFont("VD-Regular", 10)
    for i, line in enumerate(dense_lines("Spacing context", 12)):
        c.drawString(MARGIN, PAGE_H - 270 - i * 28, line)
    footer(c, case)


@add_case(
    TestCase(
        "T47",
        "Mirrored native text",
        "transforms",
        "visual_authority",
        "rejected",
        ["reading_order_implausible"],
        False,
        "mirrored text",
        "Negative horizontal scaling creates mirrored glyph geometry.",
    )
)
def t47(c, case):
    header(c, case)
    c.saveState()
    c.translate(PAGE_W - MARGIN, PAGE_H - 170)
    c.scale(-1, 1)
    c.setFont("VD-Bold", 18)
    c.drawString(0, 0, "MIRRORED TEXT 2026 AMOUNT 950.00")
    c.restoreState()
    c.setFont("VD-Regular", 10)
    c.drawString(
        MARGIN,
        PAGE_H - 230,
        "The visible line is intentionally mirrored for geometry and order testing.",
    )
    footer(c, case)


@add_case(
    TestCase(
        "T48",
        "Sheared and skewed native text",
        "transforms",
        "native_authority",
        "accepted",
        ["reading_order_provisional"],
        True,
        "slanted text",
        "Text uses a shear transformation but remains readable.",
    )
)
def t48(c, case):
    header(c, case)
    c.saveState()
    c.transform(1, 0.25, 0.3, 1, 50, 0)
    c.setFont("VD-Bold", 17)
    c.drawString(MARGIN, PAGE_H - 230, "SHEARED NATIVE TEXT 12345")
    c.restoreState()
    c.setFont("VD-Regular", 10)
    for i, line in enumerate(dense_lines("Shear context", 12)):
        c.drawString(MARGIN, PAGE_H - 300 - i * 28, line)
    footer(c, case)


@add_case(
    TestCase(
        "T49",
        "Individually rotated words",
        "transforms",
        "native_authority",
        "accepted",
        ["reading_order_provisional"],
        True,
        "words at multiple angles",
        "Word boxes and order must account for local rotations.",
    )
)
def t49(c, case):
    header(c, case)
    words = ["ROTATE", "ACCOUNT", "BALANCE", "DATE", "TOTAL", "STATUS"]
    for i, wrd in enumerate(words):
        c.saveState()
        c.translate(110 + i * 75, 500 + (i % 2) * 80)
        c.rotate(i * 17 - 35)
        c.setFont("VD-Bold", 13)
        c.drawCentredString(0, 0, wrd)
        c.restoreState()
    c.setFont("VD-Regular", 10)
    c.drawString(
        MARGIN, 350, "Local rotations must not produce NaN, inverted or out-of-bounds boxes."
    )
    footer(c, case)


@add_case(
    TestCase(
        "T50",
        "Visible text rendered only as raster image",
        "image_text",
        "visual_authority",
        "absent",
        ["native_text_absent", "image_dominant_page"],
        False,
        "text is readable but not selectable",
        "Simulates text converted to outlines or image pixels. Phase 3 routes "
        "empty native as visual_authority/absent.",
    )
)
def t50(c, case):
    img = make_page_image("T50 - TEXT AS IMAGE / OUTLINES", SCAN_LINES)
    place_full_page_image(c, img, case)


@add_case(
    TestCase(
        "T51",
        "Handwriting-like raster page",
        "handwriting",
        "image_authority",
        "rejected",
        ["native_text_absent", "handwriting_expected"],
        False,
        "handwritten notes",
        "Synthetic cursive-like image for later handwriting routing.",
    )
)
def t51(c, case):
    img = make_page_image(
        "T51 - HANDWRITING-LIKE PAGE",
        [
            "Clinical note: synthetic handwriting example",
            "Date: 2026-07-23",
            "Assessment: test-only content",
        ],
        handwriting=True,
    )
    place_full_page_image(c, img, case)


@add_case(
    TestCase(
        "T52",
        "Low-resolution scan",
        "image_quality",
        "visual_authority",
        "rejected",
        ["low_resolution_image", "native_text_absent"],
        False,
        "pixelated scan",
        "A 75-DPI page is scaled to full size.",
    )
)
def t52(c, case):
    img = make_page_image("T52 - LOW RESOLUTION SCAN", SCAN_LINES, low_res=True)
    place_full_page_image(c, img.resize((1240, 1754), Image.Resampling.NEAREST), case)


@add_case(
    TestCase(
        "T53",
        "Skewed photographed document",
        "image_quality",
        "visual_authority",
        "rejected",
        ["skewed_or_photographed_page"],
        False,
        "perspective-distorted page",
        "Simulates a phone photograph with perspective distortion.",
    )
)
def t53(c, case):
    img = make_page_image("T53 - PHOTOGRAPHED DOCUMENT", SCAN_LINES, perspective=True)
    place_full_page_image(c, img, case)


@add_case(
    TestCase(
        "T54",
        "Bilevel fax-like scan",
        "image_quality",
        "visual_authority",
        "rejected",
        ["bilevel_scan", "native_text_absent"],
        False,
        "black-and-white fax appearance",
        "One-bit thresholding simulates fax and CCITT-style content.",
    )
)
def t54(c, case):
    img = make_page_image("T54 - BILEVEL FAX-LIKE SCAN", SCAN_LINES, bilevel=True)
    place_full_page_image(c, img, case)


@add_case(
    TestCase(
        "T55",
        "JPEG-compressed photo page",
        "image_codecs",
        "visual_authority",
        "absent",
        ["native_text_absent", "image_dominant_page"],
        False,
        "photo-style JPEG renders",
        "Tests DCT/JPEG image rendering. Phase 3 routes empty native as visual_authority/absent.",
    )
)
def t55(c, case):
    w, h = 1240, 1754
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (
                int(30 + 180 * x / w),
                int(50 + 150 * y / h),
                int(120 + 100 * (x + y) / (w + h)),
            )
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT_BOLD, 42)
    d.rectangle((40, 40, 1200, 150), fill=(255, 255, 255))
    d.text((70, 70), "T55 - JPEG PHOTO / DCT RENDER TEST", font=f, fill=(20, 30, 40))
    place_full_page_image(c, img, case, jpeg=True)


@add_case(
    TestCase(
        "T56",
        "PNG alpha transparency and soft mask",
        "image_codecs",
        "native_authority",
        "accepted",
        [],
        True,
        "transparent shapes render",
        "Transparent raster overlays sit behind clean native text.",
    )
)
def t56(c, case):
    header(c, case)
    img = Image.new("RGBA", (900, 700), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    for i in range(12):
        a = 50 + i * 12
        d.ellipse(
            (40 + i * 55, 50 + i * 35, 420 + i * 30, 430 + i * 20),
            fill=(30 + i * 12, 100, 220 - i * 10, a),
        )
    p = WORK_DIR / "T56-alpha.png"
    img.save(p)
    c.drawImage(str(p), 70, 160, width=450, height=350, mask="auto")
    c.setFont("VD-Bold", 18)
    c.drawString(MARGIN, PAGE_H - 150, "NATIVE TEXT ABOVE TRANSPARENT PNG")
    c.setFont("VD-Regular", 10)
    c.drawString(MARGIN, PAGE_H - 190, "Alpha transparency must not blank or corrupt the page.")
    footer(c, case)


@add_case(
    TestCase(
        "T57",
        "CMYK image rendering",
        "image_codecs",
        "native_authority",
        "accepted",
        [],
        True,
        "CMYK colour bars render",
        "CMYK JPEG image plus clean native labels.",
    )
)
def t57(c, case):
    header(c, case)
    img = Image.new("CMYK", (900, 500), "white")
    d = ImageDraw.Draw(img)
    colors_cmyk = [(255, 0, 0, 0), (0, 255, 0, 0), (0, 0, 255, 0), (0, 0, 0, 255), (120, 80, 0, 10)]
    for i, col in enumerate(colors_cmyk):
        d.rectangle((i * 180, 0, (i + 1) * 180, 500), fill=col)
    p = WORK_DIR / "T57-cmyk.jpg"
    img.save(p, "JPEG", quality=90)
    c.drawImage(str(p), MARGIN, 230, width=PAGE_W - 2 * MARGIN, height=300)
    c.setFont("VD-Regular", 10)
    c.drawString(MARGIN, 190, "CMYK cyan, magenta, yellow, black and mixed bars should be visible.")
    footer(c, case)


@add_case(
    TestCase(
        "T58",
        "High vector-object count stress page",
        "performance",
        "native_authority",
        "accepted",
        ["bounded_processing_required"],
        True,
        "thousands of vector marks",
        "Tests renderer and parser performance without malformed syntax.",
    )
)
def t58(c, case):
    header(c, case)
    c.setLineWidth(0.2)
    for r in range(70):
        for col in range(45):
            x = 40 + col * 11.5
            y = 80 + r * 9.5
            c.setFillColorRGB((col % 7) / 7, (r % 9) / 9, ((r + col) % 11) / 11)
            c.rect(x, y, 7, 5, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont("VD-Regular", 8)
    c.drawString(MARGIN, 55, "Approximately 3,150 vector rectangles; processing must stay bounded.")
    footer(c, case)


@add_case(
    TestCase(
        "T59",
        "High native character count stress page",
        "performance",
        "native_authority",
        "accepted",
        ["bounded_processing_required"],
        True,
        "dense tiny native text",
        "Thousands of characters test safety limits and deterministic IDs.",
    )
)
def t59(c, case):
    header(c, case)
    c.setFont("VD-Regular", 4.5)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    y = PAGE_H - 110
    for r in range(115):
        line = " ".join(alphabet[(r + i) % len(alphabet)] * 2 for i in range(52))
        c.drawString(25, y - r * 6.3, line)
    footer(c, case)


@add_case(
    TestCase(
        "T60",
        "AcroForm fields and widget values",
        "forms",
        "native_authority",
        "accepted",
        ["form_widgets_present"],
        True,
        "interactive fields visible",
        "Text field, checkbox and radio buttons are interactive annotations.",
    )
)
def t60(c, case):
    header(c, case)
    c.setFont("VD-Regular", 10)
    c.drawString(MARGIN, PAGE_H - 150, "Claim number:")
    c.acroForm.textfield(
        name="vd_claim_number",
        x=MARGIN + 110,
        y=PAGE_H - 165,
        width=190,
        height=22,
        value="VD-CLM-000123",
        borderStyle="inset",
    )
    c.drawString(MARGIN, PAGE_H - 205, "Verified:")
    c.acroForm.checkbox(
        name="vd_verified", x=MARGIN + 110, y=PAGE_H - 217, buttonStyle="check", checked=True
    )
    c.drawString(MARGIN, PAGE_H - 255, "Authority choice:")
    c.acroForm.radio(
        name="vd_authority",
        value="native",
        selected=True,
        x=MARGIN + 120,
        y=PAGE_H - 268,
        buttonStyle="circle",
    )
    c.drawString(MARGIN + 140, PAGE_H - 260, "Native")
    c.acroForm.radio(
        name="vd_authority",
        value="visual",
        selected=False,
        x=MARGIN + 220,
        y=PAGE_H - 268,
        buttonStyle="circle",
    )
    c.drawString(MARGIN + 240, PAGE_H - 260, "Visual")
    c.drawString(
        MARGIN,
        PAGE_H - 315,
        "Visible labels are native text; field values may be stored separately.",
    )
    footer(c, case)


@add_case(
    TestCase(
        "T61",
        "Link, highlight, note and free-text annotations",
        "annotations",
        "native_authority",
        "accepted",
        ["annotations_present"],
        True,
        "annotations should render",
        "Viewer must expose and render several annotation types.",
        postprocess={"annotations": True},
    )
)
def t61(c, case):
    header(c, case)
    c.setFont("VD-Regular", 12)
    c.drawString(MARGIN, PAGE_H - 160, "Highlighted reference phrase: SYNTHETIC ANNOTATION TARGET")
    c.setFillColor(colors.blue)
    c.drawString(MARGIN, PAGE_H - 220, "Open safe example link")
    c.setFillColor(colors.black)
    c.drawString(
        MARGIN, PAGE_H - 280, "A note icon and free-text annotation should appear on this page."
    )
    footer(c, case)


@add_case(
    TestCase(
        "T62",
        "Appearance-only fake redaction",
        "redaction",
        "visual_authority",
        "rejected",
        ["visible_native_disagreement", "redaction_risk"],
        False,
        "black box hides live text",
        "Underlying native text remains extractable beneath a black rectangle.",
    )
)
def t62(c, case):
    header(c, case)
    c.setFont("VD-Bold", 15)
    c.drawString(MARGIN, PAGE_H - 160, "VISIBLE LABEL: ACCOUNT IDENTIFIER")
    c.setFont("VD-Regular", 14)
    c.drawString(MARGIN, PAGE_H - 220, "UNDERLYING LIVE TEXT: VD-SECRET-99999")
    c.setFillColor(colors.black)
    c.rect(MARGIN - 3, PAGE_H - 238, 360, 28, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont("VD-Regular", 10)
    c.drawString(
        MARGIN,
        PAGE_H - 280,
        "The black rectangle is not true redaction; native extraction can still reveal text.",
    )
    footer(c, case)


@add_case(
    TestCase(
        "T63",
        "Watermark and stamp over content",
        "overlays",
        "native_authority",
        "accepted",
        ["overlay_present"],
        True,
        "watermark overlays text",
        "Large rotated watermark and visible stamp.",
    )
)
def t63(c, case):
    header(c, case)
    c.setFont("VD-Regular", 10)
    for i, line in enumerate(dense_lines("Watermarked body", 17)):
        c.drawString(MARGIN, PAGE_H - 145 - i * 30, line)
    c.saveState()
    c.setFillAlpha(0.18)
    c.setFillColor(colors.red)
    c.translate(PAGE_W / 2, PAGE_H / 2)
    c.rotate(35)
    c.setFont("VD-Bold", 58)
    c.drawCentredString(0, 0, "SYNTHETIC COPY")
    c.restoreState()
    c.setStrokeColor(colors.red)
    c.setLineWidth(4)
    c.rect(PAGE_W - 205, 95, 150, 55, stroke=1, fill=0)
    c.setFillColor(colors.red)
    c.setFont("VD-Bold", 18)
    c.drawCentredString(PAGE_W - 130, 115, "RECEIVED")
    footer(c, case)


@add_case(
    TestCase(
        "T64",
        "Barcode and QR visual content",
        "barcodes",
        "native_authority",
        "accepted",
        ["barcode_regions_present"],
        True,
        "QR and barcode-like regions visible",
        "Visual codes coexist with ordinary native labels.",
    )
)
def t64(c, case):
    import qrcode

    header(c, case)
    c.setFont("VD-Bold", 16)
    c.drawString(MARGIN, PAGE_H - 150, "REFERENCE: VD-QR-2026-0001")
    qr = qrcode.QRCode(version=3, box_size=6, border=2)
    qr.add_data("VERIDEMAND:SYNTHETIC:VD-QR-2026-0001")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    p = WORK_DIR / "T64-qr.png"
    img.save(p)
    c.drawImage(str(p), MARGIN, 260, width=220, height=220)
    # barcode-like bars
    x = 330
    random.seed(64)
    for i in range(90):
        bw = random.choice([1, 2, 3])
        c.setFillColor(colors.black if i % 2 == 0 else colors.white)
        c.rect(x, 310, bw * 1.6, 160, stroke=0, fill=1)
        x += bw * 1.6
    c.setFillColor(colors.black)
    c.setFont("VD-Regular", 10)
    c.drawString(330, 285, "VD640001234567890")
    footer(c, case)


@add_case(
    TestCase(
        "T65",
        "Truly blank page",
        "blank_pages",
        "visual_authority",
        "absent",
        ["native_text_absent", "blank_page"],
        False,
        "page is intentionally blank",
        "No visible or native content; identified only by page number and manifest. "
        "Phase 3 routes as visual_authority/absent; blank_page is future-phase.",
    )
)
def t65(c, case):
    # Intentionally no drawing at all.
    return


@add_case(
    TestCase(
        "T66",
        "Optional Content Group (layer)",
        "optional_content",
        "native_authority",
        "accepted",
        ["optional_content_present"],
        True,
        "green layer rectangle visible by default",
        "A page-level optional layer is added during post-processing.",
        postprocess={"ocg": True},
    )
)
def t66(c, case):
    header(c, case)
    c.setFont("VD-Regular", 12)
    c.drawString(
        MARGIN,
        PAGE_H - 155,
        "A green optional-content rectangle should appear inside the outlined box.",
    )
    c.setStrokeColor(colors.green)
    c.rect(MARGIN, 360, PAGE_W - 2 * MARGIN, 140, stroke=1, fill=0)
    c.setFont("VD-Regular", 9)
    c.drawString(
        MARGIN, 320, "The layer is ON by default. A capable viewer may allow it to be hidden."
    )
    footer(c, case)


@add_case(
    TestCase(
        "T67",
        "Repeated Form XObject content",
        "xobjects",
        "native_authority",
        "accepted",
        ["repeated_xobject_present"],
        True,
        "many repeated mini-cards",
        "The same form XObject is reused many times.",
    )
)
def t67(c, case):
    header(c, case)
    c.beginForm("vd_card", 0, 0, 120, 45)
    c.setFillColor(colors.HexColor("#EAF2F8"))
    c.rect(0, 0, 120, 45, stroke=1, fill=1)
    c.setFillColor(colors.HexColor("#16324F"))
    c.setFont("VD-Bold", 8)
    c.drawString(8, 27, "FORM XOBJECT")
    c.setFont("VD-Regular", 7)
    c.drawString(8, 12, "Reusable synthetic card")
    c.endForm()
    for r in range(9):
        for col in range(4):
            c.saveState()
            c.translate(MARGIN + col * 128, PAGE_H - 150 - r * 62)
            c.doForm("vd_card")
            c.restoreState()
    footer(c, case)


@add_case(
    TestCase(
        "T68",
        "Clipped text and graphics",
        "clipping",
        "native_authority",
        "accepted",
        ["clipped_content_present"],
        True,
        "text clipped to a window",
        "Content extends beyond a clipping path.",
    )
)
def t68(c, case):
    header(c, case)
    p = c.beginPath()
    p.rect(MARGIN, 300, PAGE_W - 2 * MARGIN, 240)
    c.saveState()
    c.clipPath(p, stroke=1, fill=0)
    c.setFont("VD-Bold", 28)
    for i in range(12):
        c.drawString(
            MARGIN - 80 + i * 8,
            480 - i * 28,
            "CLIPPED SYNTHETIC TEXT EXTENDS OUTSIDE THE WINDOW 12345",
        )
    c.restoreState()
    c.setFont("VD-Regular", 10)
    c.drawString(MARGIN, 260, "Only the portion inside the outlined rectangle should be visible.")
    footer(c, case)


@add_case(
    TestCase(
        "T69",
        "Annotation-only visible text",
        "annotations",
        "native_authority",
        "accepted",
        ["annotation_text_separate"],
        True,
        "free-text annotation visible",
        "Visible text is added as a FreeText annotation rather than page content.",
        postprocess={"free_text_annotation": True},
    )
)
def t69(c, case):
    header(c, case)
    c.setFont("VD-Regular", 11)
    c.drawString(
        MARGIN,
        PAGE_H - 160,
        "The box below should contain text supplied only by an annotation appearance.",
    )
    c.setStrokeColor(colors.blue)
    c.rect(MARGIN, 380, PAGE_W - 2 * MARGIN, 120, stroke=1, fill=0)
    footer(c, case)


@add_case(
    TestCase(
        "T70",
        "Marked-content ActualText mismatch",
        "semantic_text",
        "visual_authority",
        "rejected",
        ["actualtext_visual_mismatch"],
        False,
        "visible value differs from semantic replacement",
        "An /ActualText replacement intentionally disagrees with the painted string.",
        postprocess={"actualtext": True},
    )
)
def t70(c, case):
    header(c, case)
    c.setFont("VD-Regular", 11)
    c.drawString(
        MARGIN,
        PAGE_H - 160,
        "The boxed line is added during post-processing with conflicting /ActualText.",
    )
    c.setStrokeColor(colors.red)
    c.rect(MARGIN, 400, PAGE_W - 2 * MARGIN, 85, stroke=1, fill=0)
    footer(c, case)


# --- PDF assembly and post-processing ---


def cover_page(c: canvas.Canvas):
    c.setPageSize(A4)
    c.setFillColor(colors.HexColor("#16324F"))
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("VD-Bold", 28)
    c.drawString(55, PAGE_H - 110, "VeriDemand Synthetic PDF Regression Corpus")
    c.setFont("VD-Regular", 14)
    c.drawString(55, PAGE_H - 150, "Version 1.0 - 70 page-scoped test cases in one uploadable PDF")
    c.setFillColor(colors.HexColor("#EAF2F8"))
    c.roundRect(55, PAGE_H - 420, PAGE_W - 110, 220, 12, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#16324F"))
    c.setFont("VD-Bold", 12)
    c.drawString(75, PAGE_H - 235, "How to use")
    c.setFont("VD-Regular", 10)
    instructions = [
        "1. Upload this single PDF to VeriDemand and process it through canonicalisation and native trust.",
        "2. Compare each T01-T70 result with the included manifest JSON and the visible page.",
        "3. Rejected pages must publish no native words or characters.",
        "4. Pages marked visual/image authority are intended for Phase 4 or later visual processing.",
        "5. Some outcomes are intentionally policy-dependent; the manifest explains the safe expectation.",
    ]
    y = PAGE_H - 270
    for line in instructions:
        c.drawString(75, y, line)
        y -= 28
    c.setFillColor(colors.white)
    c.setFont("VD-Bold", 11)
    c.drawString(55, 135, "Important limitation")
    c.setFont("VD-Regular", 9)
    draw_wrapped(
        c,
        "Encryption, digital signatures, malformed xref/trailer damage, embedded attachments and document-open JavaScript are document-scoped. They are not included because adding them would affect or block the entire combined PDF rather than one page.",
        55,
        112,
        PAGE_W - 110,
        font="VD-Regular",
        size=9,
        leading=13,
    )
    c.setFont("VD-Regular", 8)
    c.drawString(
        55, 48, "Entirely synthetic. No private, medical, legal or customer data is included."
    )
    c.showPage()


def generate_base():
    c = canvas.Canvas(str(BASE_PDF), pagesize=A4, pageCompression=1)
    c.setTitle("VeriDemand Synthetic PDF Regression Corpus v1.0")
    c.setAuthor("OpenAI - synthetic test fixture")
    c.setSubject("Page-scoped PDF ingestion, viewer, extraction and trust-gate regression cases")
    cover_page(c)
    for case, builder in zip(CASES, BUILDERS):
        c.setPageSize(case.page_size)
        builder(c, case)
        c.showPage()
    c.save()


def append_stream(writer: PdfWriter, page, data: bytes):
    existing = page.get_contents()
    existing_data = existing.get_data() if existing is not None else b""
    stream = DecodedStreamObject()
    stream.set_data(existing_data + b"\n" + data)
    page[NameObject("/Contents")] = writer._add_object(stream)


def add_optional_content(writer: PdfWriter, page):
    ocg = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/OCG"),
            NameObject("/Name"): TextStringObject("VeriDemand Optional Test Layer"),
        }
    )
    ocg_ref = writer._add_object(ocg)
    root = writer._root_object
    root[NameObject("/OCProperties")] = DictionaryObject(
        {
            NameObject("/OCGs"): ArrayObject([ocg_ref]),
            NameObject("/D"): DictionaryObject(
                {
                    NameObject("/Name"): TextStringObject("VeriDemand layer configuration"),
                    NameObject("/Order"): ArrayObject([ocg_ref]),
                    NameObject("/ON"): ArrayObject([ocg_ref]),
                    NameObject("/OFF"): ArrayObject([]),
                }
            ),
        }
    )
    resources = page.get("/Resources")
    if hasattr(resources, "get_object"):
        resources = resources.get_object()
    if resources is None:
        resources = DictionaryObject()
        page[NameObject("/Resources")] = resources
    props = resources.get("/Properties")
    if hasattr(props, "get_object"):
        props = props.get_object()
    if props is None:
        props = DictionaryObject()
        resources[NameObject("/Properties")] = props
    props[NameObject("/VDOCG")] = ocg_ref
    ops = b"q\n/OC /VDOCG BDC\n0.15 0.72 0.35 rg\n55 380 485 100 re f\nEMC\nQ\n"
    append_stream(writer, page, ops)


def add_actualtext(writer: PdfWriter, page):
    resources = page.get("/Resources")
    if hasattr(resources, "get_object"):
        resources = resources.get_object()
    fonts = resources.get("/Font") if resources else None
    if hasattr(fonts, "get_object"):
        fonts = fonts.get_object()
    font_name = next(iter(fonts.keys())) if fonts else NameObject("/F1")
    ops = (
        b"q\n/Span << /ActualText (SEMANTIC VALUE 99999 - INTENTIONALLY WRONG) >> BDC\n"
        b"BT\n"
        + str(font_name).encode("ascii")
        + b" 18 Tf\n1 0 0 1 70 435 Tm\n(VISIBLE VALUE 12345 - CORRECT ON PAGE) Tj\nET\nEMC\nQ\n"
    )
    append_stream(writer, page, ops)


def postprocess():
    writer = PdfWriter(clone_from=str(BASE_PDF))
    # Page 0 is cover; cases begin at page index 1.
    for idx, case in enumerate(CASES, start=1):
        pp = case.postprocess or {}
        page = writer.pages[idx]
        if "rotate" in pp:
            page.rotate(pp["rotate"])
        if "cropbox" in pp:
            x0, y0, x1, y1 = pp["cropbox"]
            page.cropbox.lower_left = (x0, y0)
            page.cropbox.upper_right = (x1, y1)
        if "mediabox" in pp:
            x0, y0, x1, y1 = pp["mediabox"]
            page.mediabox.lower_left = (x0, y0)
            page.mediabox.upper_right = (x1, y1)
            page.cropbox.lower_left = (x0, y0)
            page.cropbox.upper_right = (x1, y1)
        if pp.get("annotations"):
            writer.add_annotation(
                idx,
                Text(
                    rect=(500, 590, 525, 615),
                    text="Synthetic note annotation - no private data",
                    open=False,
                ),
            )
            quad = ArrayObject(
                [
                    FloatObject(42),
                    FloatObject(688),
                    FloatObject(410),
                    FloatObject(688),
                    FloatObject(42),
                    FloatObject(670),
                    FloatObject(410),
                    FloatObject(670),
                ]
            )
            writer.add_annotation(
                idx,
                Highlight(
                    rect=(40, 665, 415, 692),
                    quad_points=quad,
                    highlight_color="ffff00",
                    printing=True,
                ),
            )
            writer.add_annotation(idx, Link(rect=(40, 610, 220, 632), url="https://example.com"))
            writer.add_annotation(
                idx,
                FreeText(
                    text="FREE-TEXT ANNOTATION",
                    rect=(250, 500, 500, 555),
                    font="Helvetica",
                    bold=True,
                    font_size="14pt",
                    font_color="003366",
                    background_color="eaf2f8",
                ),
            )
        if pp.get("free_text_annotation"):
            writer.add_annotation(
                idx,
                FreeText(
                    text="VISIBLE ONLY AS A FREE-TEXT ANNOTATION",
                    rect=(60, 405, 525, 475),
                    font="Helvetica",
                    bold=True,
                    font_size="16pt",
                    font_color="003366",
                    background_color="eaf2f8",
                ),
            )
        if pp.get("ocg"):
            add_optional_content(writer, page)
        if pp.get("actualtext"):
            add_actualtext(writer, page)
    # Add outline entries for quick navigation.
    writer.add_outline_item("Cover and instructions", 0)
    for idx, case in enumerate(CASES, start=1):
        writer.add_outline_item(f"{case.test_id} - {case.title}", idx)
    writer.add_metadata(
        {
            "/Title": "VeriDemand Synthetic PDF Regression Corpus v1.0",
            "/Author": "OpenAI synthetic fixture generator",
            "/Subject": "70 page-scoped PDF regression cases",
            "/Keywords": "VeriDemand synthetic PDF regression OCR native text trust gate viewer coordinates",
        }
    )
    with open(FINAL_PDF, "wb") as f:
        writer.write(f)


def write_manifest():
    data = {
        "document_id": "veridemand_synthetic_pdf_regression_corpus",
        "version": "1.0.0",
        "generated_on": "2026-07-23",
        "pdf_filename": FINAL_PDF.name,
        "page_count_including_cover": 1 + len(CASES),
        "scope": "page-scoped cases in one healthy combined PDF",
        "document_scoped_exclusions": [
            "password encryption",
            "digital signature validation",
            "malformed xref or trailer",
            "document-open JavaScript",
            "embedded file attachment",
            "linearisation corruption",
            "object-stream corruption",
        ],
        "privacy": "Entirely synthetic; no private or real patient data.",
        "pages": [],
    }
    for i, case in enumerate(CASES, start=2):
        d = asdict(case)
        d["page_number"] = i
        d["postprocess"] = case.postprocess or {}
        d["page_size_points"] = list(case.page_size)
        d.pop("page_size", None)
        if not d.get("acceptable_outcomes"):
            d.pop("acceptable_outcomes", None)
        data["pages"].append(d)
    MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def replace_case_page(test_id: str) -> None:
    """Rebuild one case page and splice it into the committed combined PDF."""

    try:
        idx = next(i for i, case in enumerate(CASES) if case.test_id == test_id)
    except StopIteration as exc:
        raise SystemExit(f"Unknown test_id {test_id!r}") from exc
    case = CASES[idx]
    builder = BUILDERS[idx]
    single = WORK_DIR / f"{test_id}-page.pdf"
    c = canvas.Canvas(str(single), pagesize=case.page_size, pageCompression=1)
    builder(c, case)
    c.showPage()
    c.save()
    reader = PdfReader(str(FINAL_PDF))
    writer = PdfWriter()
    page_index = idx + 1  # cover at 0
    for i, page in enumerate(reader.pages):
        if i == page_index:
            writer.add_page(PdfReader(str(single)).pages[0])
        else:
            writer.add_page(page)
    if reader.metadata:
        writer.add_metadata({k: v for k, v in reader.metadata.items() if v is not None})
    with open(FINAL_PDF, "wb") as f:
        writer.write(f)
    print(f"Replaced {test_id} (PDF page {page_index + 1}) in {FINAL_PDF}")


def validate():
    reader = PdfReader(str(FINAL_PDF))
    assert len(reader.pages) == 1 + len(CASES), (len(reader.pages), len(CASES))
    # Basic structural access over every page.
    for i, p in enumerate(reader.pages):
        _ = p.mediabox.width
        _ = p.mediabox.height
        if i not in (65,):
            try:
                p.extract_text()
            except Exception as exc:
                raise RuntimeError(f"pypdf extraction failed on page {i + 1}: {exc}")
    print(f"Created {FINAL_PDF} ({FINAL_PDF.stat().st_size:,} bytes, {len(reader.pages)} pages)")


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 3 and sys.argv[1] == "--replace-page":
        replace_case_page(sys.argv[2])
    else:
        generate_base()
        postprocess()
        write_manifest()
        validate()

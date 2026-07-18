"""
Isolated OCR benchmark spike for VeriDemand readiness.
Stack: pdfplumber (native) + pypdfium2 (render) + PaddleOCR.
Coordinates: normalized top-left [0,1] per prototype §7.3.
Never promotes low-confidence critical-looking values to verified facts.
"""
from __future__ import annotations

import json
import re
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium
import psutil
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docs" / "example"
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)

# Provisional knobs from docs/modules/03-ocr-thresholds.md
NATIVE_MIN_CHARS = 40
NATIVE_MIN_TEXT_COVERAGE = 0.02
NATIVE_MAX_REPLACEMENT_RATIO = 0.05
OCR_RENDER_DPI = 200
OCR_RETRY_DPI = 300
OCR_PAGE_MEAN_CONF_LOW = 0.55
OCR_PAGE_MEAN_CONF_RETRY_TRIGGER = 0.70
CRITICAL_CONF_BAND_LOW = 0.70  # below → never treat as verified candidate

# Patterns that look critical — still only "candidates", never verified
CRITICAL_PATTERNS = [
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\$\s?\d[\d,]*\.?\d*"),
    re.compile(r"\b\d{5}[A-Z0-9-]{3,}\b", re.I),
    re.compile(r"\bCPT\b|\bICD\b|\bDOI\b|\bDOL\b", re.I),
]


@dataclass
class TokenOut:
    text: str
    confidence: float
    polygon_norm: list[list[float]]
    method: str
    verified_fact: bool = False  # always False in this spike
    review_flag: str | None = None


@dataclass
class PageResult:
    source: str
    page_number: int  # 1-based
    route: str
    native_char_count: int = 0
    native_word_count: int = 0
    native_text_coverage: float = 0.0
    ocr_token_count: int = 0
    mean_ocr_confidence: float | None = None
    dpi_used: int | None = None
    ms_native: float = 0.0
    ms_render: float = 0.0
    ms_ocr: float = 0.0
    ms_total: float = 0.0
    peak_rss_mb: float | None = None
    warnings: list[str] = field(default_factory=list)
    tokens_sample: list[dict] = field(default_factory=list)
    overlay_path: str | None = None
    error: str | None = None


def rss_mb() -> float:
    return psutil.Process().memory_info().rss / (1024 * 1024)


def select_route(chars: int, coverage: float, repl_ratio: float, warnings: list[str], cid_ratio: float = 0.0) -> str:
    if cid_ratio > 0.25:
        warnings.append("native_cid_encoding_high")
        return "ocr"
    if repl_ratio > NATIVE_MAX_REPLACEMENT_RATIO:
        return "ocr"
    if chars < NATIVE_MIN_CHARS or coverage < NATIVE_MIN_TEXT_COVERAGE:
        return "ocr"
    if "native_replacement_ratio_high" in warnings:
        return "ocr"
    return "native"


def score_native(page) -> tuple[int, int, float, float, float, list[str]]:
    warnings: list[str] = []
    words = page.extract_words() or []
    text = page.extract_text() or ""
    chars = len(text.replace("\n", "").replace(" ", ""))
    width = float(page.width or 1)
    height = float(page.height or 1)
    area = width * height
    word_area = 0.0
    cid_count = 0
    for w in words:
        word_area += max(0.0, (w["x1"] - w["x0"])) * max(0.0, (w["bottom"] - w["top"]))
        if "(cid:" in w["text"]:
            cid_count += 1
    coverage = word_area / area if area else 0.0
    replacement = text.count("\ufffd") + text.count("\x00")
    repl_ratio = replacement / max(len(text), 1)
    cid_ratio = cid_count / max(len(words), 1)
    if chars < NATIVE_MIN_CHARS:
        warnings.append("native_char_count_below_min")
    if coverage < NATIVE_MIN_TEXT_COVERAGE:
        warnings.append("native_text_coverage_below_min")
    if repl_ratio > NATIVE_MAX_REPLACEMENT_RATIO:
        warnings.append("native_replacement_ratio_high")
    if cid_ratio > 0.25:
        warnings.append("native_cid_ratio_high")
    return chars, len(words), coverage, repl_ratio, cid_ratio, warnings


def render_page(pdf_path: Path, page_index: int, dpi: int) -> Image.Image:
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        page = doc[page_index]
        scale = dpi / 72.0
        bitmap = page.render(scale=scale)
        pil = bitmap.to_pil()
        return pil.convert("RGB")
    finally:
        doc.close()


def paddle_boxes_to_norm(box, img_w: int, img_h: int) -> list[list[float]]:
    # Paddle returns [[x,y], ...] in pixel space, origin top-left
    pts = []
    for x, y in box:
        pts.append([round(float(x) / img_w, 6), round(float(y) / img_h, 6)])
    return pts


def _parse_paddle_result(result, img_w: int, img_h: int) -> tuple[list[TokenOut], list[float], list[str]]:
    """Normalize classic ocr.ocr and newer predict() result shapes."""
    warnings: list[str] = []
    tokens: list[TokenOut] = []
    confs: list[float] = []
    if result is None:
        return tokens, confs, ["ocr_empty_result"]

    # Newer PaddleOCR may return list[dict] with keys dt_polys / rec_texts / rec_scores
    if isinstance(result, list) and result and isinstance(result[0], dict):
        for page in result:
            polys = page.get("dt_polys") or page.get("rec_polys") or []
            texts = page.get("rec_texts") or []
            scores = page.get("rec_scores") or []
            for box, text, conf in zip(polys, texts, scores):
                conf_f = float(conf)
                confs.append(conf_f)
                # box may be ndarray
                box_list = [[float(x), float(y)] for x, y in box]
                tokens.append(
                    _token_from_ocr(text, conf_f, paddle_boxes_to_norm(box_list, img_w, img_h))
                )
        if not tokens:
            warnings.append("ocr_empty_result")
        return tokens, confs, warnings

    # Classic: result[0] = list of [box, (text, conf)]
    lines = result[0] if result and isinstance(result[0], list) else result
    if lines is None:
        return tokens, confs, ["ocr_null_lines"]
    for item in lines:
        if not item:
            continue
        box, meta = item[0], item[1]
        text, conf = meta[0], float(meta[1])
        confs.append(conf)
        tokens.append(_token_from_ocr(text, conf, paddle_boxes_to_norm(box, img_w, img_h)))
    if not tokens:
        warnings.append("ocr_empty_result")
    return tokens, confs, warnings


def _token_from_ocr(text: str, conf: float, poly: list[list[float]]) -> TokenOut:
    review = None
    looks_critical = any(p.search(text) for p in CRITICAL_PATTERNS)
    if conf < CRITICAL_CONF_BAND_LOW:
        review = "low_confidence"
        if looks_critical:
            review = "low_confidence_critical_candidate"
    elif looks_critical and conf < 0.90:
        review = "mid_confidence_critical_candidate"
    return TokenOut(
        text=text,
        confidence=conf,
        polygon_norm=poly,
        method="ocr",
        verified_fact=False,
        review_flag=review,
    )


def run_ocr(image: Image.Image, ocr_engine) -> tuple[list[TokenOut], float, list[str]]:
    warnings: list[str] = []
    import numpy as np

    arr = np.array(image)
    w, h = image.size
    result = None
    # Prefer classic PaddleOCR 2.x API in the spike venv.
    if hasattr(ocr_engine, "ocr"):
        try:
            result = ocr_engine.ocr(arr, cls=True)
        except TypeError:
            result = ocr_engine.ocr(arr)
    if result is None and hasattr(ocr_engine, "predict"):
        result = ocr_engine.predict(arr)
    tokens, confs, parse_warn = _parse_paddle_result(result, w, h)
    warnings.extend(parse_warn)
    mean_conf = sum(confs) / len(confs) if confs else 0.0
    if mean_conf < OCR_PAGE_MEAN_CONF_LOW:
        warnings.append("page_mean_confidence_low")
    return tokens, mean_conf, warnings


def draw_overlay(image: Image.Image, tokens: list[TokenOut], path: Path) -> None:
    img = image.copy()
    draw = ImageDraw.Draw(img)
    w, h = img.size
    for t in tokens:
        pts = [(p[0] * w, p[1] * h) for p in t.polygon_norm]
        color = (0, 180, 0) if (t.confidence >= 0.90) else (220, 140, 0) if t.confidence >= 0.70 else (220, 40, 40)
        if len(pts) >= 2:
            draw.polygon(pts, outline=color)
    img.save(path)


def process_page(
    pdf_path: Path,
    page_number: int,
    ocr_engine,
    force_ocr: bool | None = None,
) -> PageResult:
    peak = rss_mb()
    t0 = time.perf_counter()
    src = pdf_path.name
    result = PageResult(source=src, page_number=page_number, route="unknown")
    try:
        t_n = time.perf_counter()
        with pdfplumber.open(str(pdf_path)) as pdf:
            page = pdf.pages[page_number - 1]
            chars, n_words, coverage, repl_ratio, cid_ratio, warnings = score_native(page)
        result.ms_native = (time.perf_counter() - t_n) * 1000
        result.native_char_count = chars
        result.native_word_count = n_words
        result.native_text_coverage = round(coverage, 6)
        result.warnings.extend(warnings)
        route = select_route(chars, coverage, repl_ratio, result.warnings, cid_ratio)
        if force_ocr is True:
            route = "ocr"
        elif force_ocr is False:
            route = "native"
        result.route = route
        peak = max(peak, rss_mb())

        tokens: list[TokenOut] = []
        mean_conf = None
        dpi_used = None

        if route == "native":
            # Capture native words as tokens with confidence 1.0 for comparison
            with pdfplumber.open(str(pdf_path)) as pdf:
                page = pdf.pages[page_number - 1]
                width = float(page.width)
                height = float(page.height)
                for w in page.extract_words() or []:
                    poly = [
                        [w["x0"] / width, w["top"] / height],
                        [w["x1"] / width, w["top"] / height],
                        [w["x1"] / width, w["bottom"] / height],
                        [w["x0"] / width, w["bottom"] / height],
                    ]
                    tokens.append(
                        TokenOut(
                            text=w["text"],
                            confidence=1.0,
                            polygon_norm=[[round(a, 6), round(b, 6)] for a, b in poly],
                            method="native",
                            verified_fact=False,
                        )
                    )
            # Still render overlay from PDF for visual QA of native boxes
            t_r = time.perf_counter()
            image = render_page(pdf_path, page_number - 1, OCR_RENDER_DPI)
            result.ms_render = (time.perf_counter() - t_r) * 1000
            dpi_used = OCR_RENDER_DPI
        else:
            dpi_used = OCR_RENDER_DPI
            t_r = time.perf_counter()
            image = render_page(pdf_path, page_number - 1, dpi_used)
            result.ms_render = (time.perf_counter() - t_r) * 1000
            peak = max(peak, rss_mb())
            t_o = time.perf_counter()
            tokens, mean_conf, ocr_warn = run_ocr(image, ocr_engine)
            result.ms_ocr = (time.perf_counter() - t_o) * 1000
            result.warnings.extend(ocr_warn)
            peak = max(peak, rss_mb())
            if mean_conf is not None and mean_conf < OCR_PAGE_MEAN_CONF_RETRY_TRIGGER:
                result.warnings.append("retry_triggered")
                dpi_used = OCR_RETRY_DPI
                t_r2 = time.perf_counter()
                image = render_page(pdf_path, page_number - 1, dpi_used)
                result.ms_render += (time.perf_counter() - t_r2) * 1000
                # light OpenCV contrast normalize
                import cv2
                import numpy as np

                arr = np.array(image)
                gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                eq = clahe.apply(gray)
                image = Image.fromarray(cv2.cvtColor(eq, cv2.COLOR_GRAY2RGB))
                t_o2 = time.perf_counter()
                tokens, mean_conf, ocr_warn2 = run_ocr(image, ocr_engine)
                result.ms_ocr += (time.perf_counter() - t_o2) * 1000
                result.warnings.extend([f"retry_{w}" for w in ocr_warn2])
                peak = max(peak, rss_mb())

        result.ocr_token_count = len(tokens)
        result.mean_ocr_confidence = round(mean_conf, 4) if mean_conf is not None else (
            1.0 if route == "native" and tokens else None
        )
        result.dpi_used = dpi_used
        # sample up to 15 tokens for report (avoid PII dump)
        result.tokens_sample = [
            {
                "text_len": len(t.text),
                "confidence": t.confidence,
                "method": t.method,
                "review_flag": t.review_flag,
                "verified_fact": t.verified_fact,
                "polygon_norm": t.polygon_norm,
            }
            for t in tokens[:15]
        ]
        low_crit = sum(1 for t in tokens if t.review_flag == "low_confidence_critical_candidate")
        if low_crit:
            result.warnings.append(f"low_confidence_critical_candidates={low_crit}")

        overlay = OUT / f"{pdf_path.stem}_p{page_number}_overlay.png"
        draw_overlay(image, tokens, overlay)
        result.overlay_path = str(overlay.relative_to(ROOT))
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        result.warnings.append("page_failed")
        result.route = result.route or "error"
        traceback.print_exc()
    result.peak_rss_mb = round(max(peak, rss_mb()), 1)
    result.ms_total = round((time.perf_counter() - t0) * 1000, 1)
    result.ms_native = round(result.ms_native, 1)
    result.ms_render = round(result.ms_render, 1)
    result.ms_ocr = round(result.ms_ocr, 1)
    return result


def main() -> None:
    jobs = [
        # force_ocr=True measures OCR path even when a usable native layer exists
        (EXAMPLE / "EG90156.pdf", [1, 2], True),
        (EXAMPLE / "Mayel Amini Dairyland Insurance 06.22.26.pdf", [1], True),
        (
            EXAMPLE / "MEDICAL RECORDS- AMINI MAYEL DOI 03-28-2026- JACKMAN LAW FIRM.pdf",
            [1, 2, 10],
            True,
        ),
        (EXAMPLE / "AMINI_MAYEL_20260706_eCW Medical Records.pdf", [1], None),  # expect native
        (EXAMPLE / "AMINI_MAYEL_20260706_eCW Billing Ledger.pdf", [1], True),  # broken native
    ]

    print("Loading PaddleOCR (first run may download models)...")
    t_load = time.perf_counter()
    from paddleocr import PaddleOCR

    # PaddleOCR 2.7.x (spike venv). Avoid 3.x on this Windows host (oneDNN/PIR crash).
    try:
        ocr_engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    except TypeError:
        ocr_engine = PaddleOCR(lang="en")
    load_ms = (time.perf_counter() - t_load) * 1000
    print(f"PaddleOCR ready in {load_ms:.0f} ms")

    pages: list[PageResult] = []
    for path, page_nums, force in jobs:
        if not path.exists():
            pages.append(
                PageResult(
                    source=path.name,
                    page_number=0,
                    route="missing",
                    warnings=["file_missing"],
                    error=f"missing {path}",
                )
            )
            continue
        for pn in page_nums:
            print(f"Processing {path.name} page {pn}...")
            pages.append(process_page(path, pn, ocr_engine, force_ocr=force))

    payload = {
        "spike": "ocr",
        "thresholds_version_referenced": "0.1-provisional",
        "coordinate_space": "normalized_top_left_0_1",
        "paddleocr_load_ms": round(load_ms, 1),
        "disclaimer": (
            "Results are measured on a few representative pages only. "
            "Do not claim general OCR accuracy from this spike. "
            "No token is promoted to a verified fact."
        ),
        "pages": [asdict(p) for p in pages],
    }
    out_json = OUT / "metrics.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_json}")
    for p in pages:
        status = p.error or "ok"
        print(
            f"  {p.source} p{p.page_number}: route={p.route} "
            f"tokens={p.ocr_token_count} mean_conf={p.mean_ocr_confidence} "
            f"total_ms={p.ms_total} peak_rss_mb={p.peak_rss_mb} ({status})"
        )


if __name__ == "__main__":
    main()

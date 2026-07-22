#!/usr/bin/env python3
"""Evaluate printed OCR on synthetic fixtures (CER/WER/IoU calibration).

Never prints private text. Synthetic transcripts are local calibration only —
not firm-approved gold and not a universal accuracy claim.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURES = ROOT / "fixtures" / "synthetic" / "ocr"


def _normalise(text: str) -> str:
    text = text.casefold().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (ca != cb)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def character_error_rate(hyp: str, ref: str) -> float:
    ref_n = _normalise(ref)
    hyp_n = _normalise(hyp)
    if not ref_n:
        return 0.0 if not hyp_n else 1.0
    return _levenshtein(hyp_n, ref_n) / max(len(ref_n), 1)


def word_error_rate(hyp: str, ref: str) -> float:
    ref_w = _normalise(ref).split()
    hyp_w = _normalise(hyp).split()
    if not ref_w:
        return 0.0 if not hyp_w else 1.0
    return _levenshtein("\0".join(hyp_w), "\0".join(ref_w)) / max(len(ref_w), 1)


def _polygon_iou(a: list[list[float]], b: list[list[float]]) -> float | None:
    """Axis-aligned IoU from polygon extents (calibration helper)."""

    try:
        ax = [p[0] for p in a]
        ay = [p[1] for p in a]
        bx = [p[0] for p in b]
        by = [p[1] for p in b]
    except (TypeError, IndexError):
        return None
    ax0, ax1 = min(ax), max(ax)
    ay0, ay1 = min(ay), max(ay)
    bx0, bx1 = min(bx), max(bx)
    by0, by1 = min(by), max(by)
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    if union <= 0:
        return None
    return inter / union


def _load_gold(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"Gold file must be a JSON object: {path}")
    return data


def _run_paddle_on_image(image_path: Path) -> tuple[str, list[dict[str, Any]]]:
    from backend.app.extraction.visual.paddle_adapter import PaddleOcrAdapter
    from backend.app.extraction.visual.worker_manager import OcrWorkerManager
    from backend.app.settings.config import Settings
    from PIL import Image

    settings = Settings(render_concurrency=1, ocr_concurrency=1, ocr_workers=1, ocr_enabled=True)
    config = OcrWorkerManager(settings).config_from_settings()
    adapter = PaddleOcrAdapter(config)
    adapter.load()
    with Image.open(image_path) as image:
        lines = adapter.recognise(image.convert("RGB"))
    text = "\n".join(line.text for line in lines)
    payloads = [
        {
            "text": line.text,
            "polygon_px": [[float(x), float(y)] for x, y in line.polygon_px],
            "score": line.recognition_score,
        }
        for line in lines
    ]
    return text, payloads


def _render_pdf_page(pdf_path: Path, dpi: float = 200.0) -> Path:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf_path))
    page = doc[0]
    scale = dpi / 72.0
    bitmap = page.render(scale=scale)
    pil = bitmap.to_pil()
    out = pdf_path.with_suffix(".render.png")
    pil.convert("RGB").save(out)
    page.close()
    doc.close()
    return out


def evaluate_case(gold_path: Path, *, fixtures_root: Path) -> dict[str, Any]:
    gold = _load_gold(gold_path)
    case_id = str(gold.get("id") or gold_path.stem.replace(".gold", ""))
    if gold.get("phase5_pending"):
        return {
            "id": case_id,
            "status": "skipped_phase5_pending",
            "cer": None,
            "wer": None,
        }

    file_name = str(gold.get("file") or "")
    source = fixtures_root / file_name
    if not source.is_file():
        return {"id": case_id, "status": "missing_fixture", "cer": None, "wer": None}

    kind = str(gold.get("kind") or "image")
    image_path = source
    cleanup: Path | None = None
    if kind == "pdf":
        cleanup = _render_pdf_page(source, dpi=float(gold.get("dpi") or 200))
        image_path = cleanup

    try:
        hyp, line_payloads = _run_paddle_on_image(image_path)
    except Exception as exc:
        return {
            "id": case_id,
            "status": "ocr_failed",
            "error_type": type(exc).__name__,
            "cer": None,
            "wer": None,
        }
    finally:
        if cleanup is not None and cleanup.exists():
            cleanup.unlink(missing_ok=True)

    ref = str(gold.get("transcript") or "")
    cer = character_error_rate(hyp, ref)
    wer = word_error_rate(hyp, ref)

    # IoU only when gold provides polygons (optional).
    ious: list[float] = []
    gold_lines = gold.get("lines") or []
    if isinstance(gold_lines, list):
        for idx, gl in enumerate(gold_lines):
            if not isinstance(gl, dict):
                continue
            poly = gl.get("polygon_px") or gl.get("bbox")
            if not isinstance(poly, list) or idx >= len(line_payloads):
                continue
            iou = _polygon_iou(line_payloads[idx]["polygon_px"], poly)
            if iou is not None:
                ious.append(iou)

    gate = str(gold.get("gate") or "clean")
    return {
        "id": case_id,
        "status": "evaluated",
        "gate": gate,
        "cer": round(cer, 4),
        "wer": round(wer, 4),
        "line_count_hyp": len(line_payloads),
        "line_count_ref": len(gold_lines) if isinstance(gold_lines, list) else 0,
        "median_line_iou": round(statistics.median(ious), 4) if ious else None,
        # Never include hypothesis/reference text in the report payload.
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--output-json", type=Path, default=None)
    args = parser.parse_args(argv)

    fixtures = args.fixtures
    if not fixtures.is_dir():
        print(f"Fixtures directory missing: {fixtures}", file=sys.stderr)
        return 2

    gold_files = sorted(fixtures.glob("*.gold.json"))
    if not gold_files:
        print("No *.gold.json files found.", file=sys.stderr)
        return 2

    model_record = ROOT / ".models" / "paddleocr" / "model-record.json"
    if not model_record.is_file():
        print(
            "OCR models absent (.models/paddleocr/model-record.json). "
            "Run pnpm models:ocr:bootstrap first.",
            file=sys.stderr,
        )
        return 2

    results = [evaluate_case(path, fixtures_root=fixtures) for path in gold_files]
    clean = [r for r in results if r.get("status") == "evaluated" and r.get("gate") == "clean"]
    degraded = [
        r for r in results if r.get("status") == "evaluated" and r.get("gate") == "degraded"
    ]
    summary = {
        "fixture_root": str(fixtures.as_posix()),
        "cases": len(results),
        "evaluated": sum(1 for r in results if r.get("status") == "evaluated"),
        "skipped_phase5_pending": sum(
            1 for r in results if r.get("status") == "skipped_phase5_pending"
        ),
        "failed": sum(1 for r in results if r.get("status") == "ocr_failed"),
        "clean_mean_cer": (
            round(statistics.mean([float(r["cer"]) for r in clean]), 4) if clean else None
        ),
        "degraded_mean_cer": (
            round(statistics.mean([float(r["cer"]) for r in degraded]), 4) if degraded else None
        ),
        "gates": {
            "clean_cer_max": 0.03,
            "degraded_cer_max": 0.15,
            "median_line_iou_min": 0.70,
        },
        "results": results,
        "disclaimer": (
            "Calibration only on synthetic fixtures. Not firm-approved gold; "
            "not a universal OCR accuracy claim."
        ),
    }

    clean_mean = summary.get("clean_mean_cer")
    degraded_mean = summary.get("degraded_mean_cer")
    clean_ok = clean_mean is None or (
        isinstance(clean_mean, (int, float)) and float(clean_mean) <= 0.03
    )
    degraded_ok = degraded_mean is None or (
        isinstance(degraded_mean, (int, float)) and float(degraded_mean) <= 0.15
    )
    failed_count = summary.get("failed", 0)
    summary["pass"] = bool(
        clean_ok and degraded_ok and isinstance(failed_count, int) and failed_count == 0
    )

    text = json.dumps(summary, indent=2, sort_keys=True)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

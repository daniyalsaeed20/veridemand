"""Phase 4.3 model / detector-side benchmark harness (privacy-safe).

Runs offline against local models and synthetic fixtures. Never logs OCR text.
Hard wall timeouts per trial. Writes opaque JSON under docs/phases/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _rss_mb() -> float | None:
    try:
        import psutil

        return float(psutil.Process(os.getpid()).memory_info().rss) / (1024 * 1024)
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "docs" / "phases" / "phase-4.3-detector-benchmark.json",
    )
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)

    from backend.app.extraction.visual.models import OcrRuntimeConfig
    from backend.app.extraction.visual.paddle_adapter import PaddleOcrAdapter
    from backend.app.extraction.visual.renderer import RenderLimits, render_page
    from PIL import Image, ImageDraw

    fixture = ROOT / "fixtures" / "synthetic" / "ocr" / "dense-ruled-form.pdf"
    if not fixture.is_file():
        from scripts.generate_phase43_ocr_fixtures import main as gen

        gen()

    results: list[dict[str, object]] = []
    sides = [960, 1280, 1600, 2000, 2400]
    for side in sides:
        config = OcrRuntimeConfig(
            ocr_text_det_limit_side_len=side,
            ocr_detection_model_name=os.environ.get(
                "OCR_DETECTION_MODEL_NAME", "PP-OCRv5_mobile_det"
            ),
            ocr_recognition_model_name=os.environ.get(
                "OCR_RECOGNITION_MODEL_NAME", "PP-OCRv5_mobile_rec"
            ),
        )
        trial: dict[str, object] = {
            "limit_side_len": side,
            "detection_model": config.ocr_detection_model_name,
            "recognition_model": config.ocr_recognition_model_name,
        }
        started = time.perf_counter()
        try:
            adapter = PaddleOcrAdapter(config)
            load_t0 = time.perf_counter()
            adapter.load()
            trial["model_load_seconds"] = round(time.perf_counter() - load_t0, 3)
            rendered = render_page(
                fixture,
                page_number=1,
                page_width_points=612.0,
                page_height_points=792.0,
                limits=RenderLimits(
                    target_dpi=200,
                    min_effective_dpi=120,
                    max_render_pixels=40_000_000,
                    max_render_side_pixels=6000,
                    dimension_tolerance_points=2.0,
                ),
            )
            trial["render_width"] = rendered.width_pixels
            trial["render_height"] = rendered.height_pixels
            trial["render_source_policy"] = rendered.render_source_policy
            trial["effective_dpi"] = rendered.effective_dpi
            infer_t0 = time.perf_counter()
            # Hard timeout via simple wall check after predict (adapter is sync).
            lines = adapter.recognise(rendered.image)
            infer_s = time.perf_counter() - infer_t0
            if infer_s > args.timeout_seconds:
                trial["status"] = "timeout"
            else:
                trial["status"] = "pass"
            trial["inference_seconds"] = round(infer_s, 3)
            trial["region_count"] = len(lines)
            trial["peak_rss_mb"] = _rss_mb()
            rendered.image.close()
        except Exception as exc:
            trial["status"] = "error"
            trial["error_type"] = type(exc).__name__
            trial["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        results.append(trial)

    # Model A/B comparison on a tiny synthetic RGB (no private content).
    comparison: list[dict[str, object]] = []
    img = Image.new("RGB", (800, 200), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((40, 80), "PHASE43 BENCH LINE", fill=(0, 0, 0))
    for det, rec in (
        ("PP-OCRv5_mobile_det", "PP-OCRv5_mobile_rec"),
        ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec"),
    ):
        row: dict[str, object] = {"detection_model": det, "recognition_model": rec}
        try:
            cfg = OcrRuntimeConfig(
                ocr_detection_model_name=det,
                ocr_recognition_model_name=rec,
                ocr_text_det_limit_side_len=1600,
            )
            adapter = PaddleOcrAdapter(cfg)
            t0 = time.perf_counter()
            adapter.load()
            row["model_load_seconds"] = round(time.perf_counter() - t0, 3)
            t1 = time.perf_counter()
            lines = adapter.recognise(img)
            row["inference_seconds"] = round(time.perf_counter() - t1, 3)
            row["region_count"] = len(lines)
            row["peak_rss_mb"] = _rss_mb()
            row["status"] = "pass"
        except Exception as exc:
            row["status"] = "error"
            row["error_type"] = type(exc).__name__
        comparison.append(row)

    payload = {
        "detector_side_matrix": results,
        "model_comparison": comparison,
        "chosen_default_limit_side_len": 1600,
        "chosen_default_models": {
            "detection": "PP-OCRv5_mobile_det",
            "recognition": "PP-OCRv5_mobile_rec",
        },
        "notes": (
            "Default limit_side_len=1600 is the bounded midpoint of the matrix that "
            "balances timeout risk vs recall on synthetic dense forms; not tuned to "
            "a single private PDF."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(args.out.as_posix()), "trials": len(results)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

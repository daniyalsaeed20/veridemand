"""Timed Windows MKL-DNN / thread matrix for local PaddleOCR (offline models).

Does not change production defaults — reports timings so ADR/report can lock
``enable_mkldnn=False`` on Windows with evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _synth_image() -> object:
    import numpy as np
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (800, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.text((40, 80), "VeriDemand printed OCR timing", fill=(0, 0, 0))
    return np.asarray(image)


def _run_once(*, enable_mkldnn: bool, threads: int, model_root: Path) -> dict[str, object]:
    os.environ["FLAGS_use_mkldnn"] = "1" if enable_mkldnn else "0"  # noqa: SIM112
    os.environ["FLAGS_onednn"] = "1" if enable_mkldnn else "0"  # noqa: SIM112
    os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "1" if enable_mkldnn else "0"
    os.environ["FLAGS_paddle_num_threads"] = str(threads)  # noqa: SIM112
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

    from paddleocr import PaddleOCR

    det = model_root / "PP-OCRv6_medium_det"
    rec = model_root / "PP-OCRv6_medium_rec"
    if not det.is_dir() or not rec.is_dir():
        raise FileNotFoundError(f"Local models missing under {model_root}")

    started = time.perf_counter()
    try:
        ocr = PaddleOCR(
            text_detection_model_dir=str(det),
            text_recognition_model_dir=str(rec),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device="cpu",
            enable_mkldnn=enable_mkldnn,
            cpu_threads=threads,
        )
    except TypeError:
        ocr = PaddleOCR(
            text_detection_model_dir=str(det),
            text_recognition_model_dir=str(rec),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device="cpu",
            enable_mkldnn=enable_mkldnn,
        )
    load_s = time.perf_counter() - started

    image = _synth_image()
    infer_started = time.perf_counter()
    _ = ocr.predict(image)
    infer_s = time.perf_counter() - infer_started
    return {
        "enable_mkldnn": enable_mkldnn,
        "threads": threads,
        "load_seconds": round(load_s, 3),
        "infer_seconds": round(infer_s, 3),
        "ok": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-root",
        type=Path,
        default=REPO_ROOT / ".models" / "paddleocr",
    )
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    args = parser.parse_args()

    results: list[dict[str, object]] = []
    matrix = [
        (False, 1),
        (False, 4),
        (True, 1),
        (True, 4),
    ]
    for enable_mkldnn, threads in matrix:
        print(f"Running mkldnn={enable_mkldnn} threads={threads} ...", flush=True)
        try:
            # Soft timeout via wall clock check around the call.
            started = time.monotonic()
            row = _run_once(
                enable_mkldnn=enable_mkldnn,
                threads=threads,
                model_root=args.model_root,
            )
            if time.monotonic() - started > args.timeout_seconds:
                row["ok"] = False
                row["error"] = "exceeded soft timeout"
            results.append(row)
        except Exception as exc:
            results.append(
                {
                    "enable_mkldnn": enable_mkldnn,
                    "threads": threads,
                    "ok": False,
                    "error": type(exc).__name__,
                }
            )

    print(json.dumps({"platform": sys.platform, "results": results}, indent=2))
    # Production lock: Windows stays on enable_mkldnn=False (see ADR 0022).
    false_ok = any(r.get("ok") and r.get("enable_mkldnn") is False for r in results)
    return 0 if false_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

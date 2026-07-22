#!/usr/bin/env python3
"""Verify local Phase 4 OCR runtime without downloading models.

Checks imports, paddle.run_check, model directories, tree hashes against
model-record.json, and one synthetic warm-up using local model dirs only.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _emit(message: str) -> None:
    print(message, flush=True)


def _tree_hash(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            rel = path.relative_to(directory).as_posix().encode("utf-8")
            digest.update(rel)
            digest.update(b"\0")
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
    return digest.hexdigest()


def _synthetic_image() -> object:
    import numpy as np
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (640, 160), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.text((24, 56), "VeriDemand OCR verify 456", fill=(0, 0, 0))
    return np.asarray(image)


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("FLAGS_onednn", "0")
    os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")

    # Block silent downloads during verify — models must already exist.
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

    from backend.app.settings.config import Settings

    settings = Settings()
    model_root = settings.ocr_model_root
    record_path = model_root / "model-record.json"
    det_dir = model_root / settings.ocr_detection_model_name
    rec_dir = model_root / settings.ocr_recognition_model_name

    if not record_path.is_file():
        _emit("ERROR: model-record.json missing. Run pnpm models:ocr:bootstrap first.")
        return 1
    if not det_dir.is_dir() or not rec_dir.is_dir():
        _emit("ERROR: Detection or recognition model directory missing.")
        return 1

    record = json.loads(record_path.read_text(encoding="utf-8"))
    det_hash = _tree_hash(det_dir)
    rec_hash = _tree_hash(rec_dir)
    if det_hash != record.get("detection_tree_hash"):
        _emit("ERROR: Detection model tree hash mismatch.")
        return 1
    if rec_hash != record.get("recognition_tree_hash"):
        _emit("ERROR: Recognition model tree hash mismatch.")
        return 1

    try:
        import paddle
        import paddleocr
        import pypdfium2
        from paddleocr import PaddleOCR

        try:
            paddle.utils.run_check()
        except Exception:
            _emit("WARNING: paddle.utils.run_check() failed; continuing with OCR warm-up.")
            traceback.print_exc()
        _emit(f"paddlepaddle={getattr(paddle, '__version__', 'unknown')}")
        _emit(f"paddleocr={getattr(paddleocr, '__version__', 'unknown')}")
        _emit(f"pypdfium2={getattr(pypdfium2, '__version__', 'unknown')}")

        ocr = PaddleOCR(
            text_detection_model_name=settings.ocr_detection_model_name,
            text_detection_model_dir=str(det_dir),
            text_recognition_model_name=settings.ocr_recognition_model_name,
            text_recognition_model_dir=str(rec_dir),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            return_word_box=True,
            device=settings.ocr_device,
            enable_hpi=False,
            enable_mkldnn=False,
            text_recognition_batch_size=1,
        )
        _ = ocr.predict(_synthetic_image())
    except Exception:
        _emit("ERROR: OCR runtime verification failed.")
        traceback.print_exc()
        return 1

    _emit("OCR runtime verification succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

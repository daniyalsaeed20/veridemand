#!/usr/bin/env python3
"""Bootstrap local PaddleOCR detector and recogniser models for Phase 4.

Downloads configured models into OCR_MODEL_ROOT, records package versions and a
deterministic model-tree hash, and runs one synthetic warm-up inference.
Never commits model binaries. Exits non-zero on any failure.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import platform
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _emit(message: str) -> None:
    print(message, flush=True)


def _tree_hash(directory: Path) -> str:
    digest = hashlib.sha256()
    if not directory.is_dir():
        raise FileNotFoundError(f"Model directory missing: {directory}")
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
    draw.text((24, 56), "VeriDemand OCR warm-up 123", fill=(0, 0, 0))
    return np.asarray(image)


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    if platform.architecture()[0] != "64bit":
        _emit("ERROR: Python must be 64-bit for PaddlePaddle.")
        return 1

    from backend.app.settings.config import Settings

    settings = Settings()
    model_root = settings.ocr_model_root
    model_root.mkdir(parents=True, exist_ok=True)

    # Prefer BOS when Hugging Face is unavailable (Windows CI / restricted nets).
    os.environ.setdefault(
        "PADDLE_PDX_MODEL_SOURCE", os.environ.get("PADDLE_PDX_MODEL_SOURCE", "BOS")
    )
    # Linux CPU runners hit OneDNN PIR conversion errors on PP-OCRv6; force plain CPU.
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("FLAGS_onednn", "0")
    os.environ.setdefault("FLAGS_enable_pir_api", "0")
    os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

    try:
        import paddle

        _emit(f"paddlepaddle={getattr(paddle, '__version__', 'unknown')}")
        paddle.utils.run_check()
    except Exception:
        _emit("ERROR: paddle.utils.run_check() failed.")
        traceback.print_exc()
        return 1

    try:
        import paddleocr
        from paddleocr import PaddleOCR
    except Exception:
        _emit("ERROR: Failed to import PaddleOCR.")
        traceback.print_exc()
        return 1

    det_dir = model_root / settings.ocr_detection_model_name
    rec_dir = model_root / settings.ocr_recognition_model_name

    _emit(
        f"Bootstrapping models into {model_root.as_posix()} "
        f"(det={settings.ocr_detection_model_name}, rec={settings.ocr_recognition_model_name})"
    )

    try:
        # Construction downloads into the PaddleX cache when dirs are missing.
        ocr = PaddleOCR(
            text_detection_model_name=settings.ocr_detection_model_name,
            text_detection_model_dir=str(det_dir) if det_dir.is_dir() else None,
            text_recognition_model_name=settings.ocr_recognition_model_name,
            text_recognition_model_dir=str(rec_dir) if rec_dir.is_dir() else None,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            return_word_box=True,
            device=settings.ocr_device,
            enable_hpi=False,
            enable_mkldnn=False,
            text_recognition_batch_size=settings.ocr_recognition_batch_size,
            text_det_limit_side_len=settings.ocr_text_det_limit_side_len,
            text_det_limit_type=settings.ocr_text_det_limit_type,
            text_det_thresh=settings.ocr_text_det_thresh,
            text_det_box_thresh=settings.ocr_text_det_box_thresh,
            text_det_unclip_ratio=settings.ocr_text_det_unclip_ratio,
            text_rec_score_thresh=0.0,
        )
        # Touch predict once so downloads finish if construction deferred them.
        with contextlib.suppress(Exception):
            _ = ocr.predict(_synthetic_image())
    except TypeError:
        # Fallback without extended kwargs if the installed paddleocr signature differs.
        ocr = PaddleOCR(
            text_detection_model_name=settings.ocr_detection_model_name,
            text_recognition_model_name=settings.ocr_recognition_model_name,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            return_word_box=True,
            device=settings.ocr_device,
            enable_hpi=False,
            enable_mkldnn=False,
            text_recognition_batch_size=settings.ocr_recognition_batch_size,
        )
        with contextlib.suppress(Exception):
            _ = ocr.predict(_synthetic_image())

    # Materialise models under OCR_MODEL_ROOT from the PaddleX cache.
    if not det_dir.is_dir() or not rec_dir.is_dir():
        import shutil

        candidates = [
            Path(r"D:\programming\caches\paddle\official_models"),
            Path.home() / ".paddlex" / "official_models",
            Path.home() / ".paddleocr",
            ROOT / ".paddleocr",
            Path(os.environ.get("PADDLE_PDX_CACHE_HOME", "")) / "official_models"
            if os.environ.get("PADDLE_PDX_CACHE_HOME")
            else None,
        ]
        for env_key in ("PADDLE_HOME", "PADDLEX_HOME"):
            raw = os.environ.get(env_key)
            if raw:
                candidates.append(Path(raw) / "official_models")

        for base in candidates:
            if base is None or not base.is_dir():
                continue
            maybe_det = base / settings.ocr_detection_model_name
            maybe_rec = base / settings.ocr_recognition_model_name
            try:
                if maybe_det.is_dir() and not det_dir.is_dir():
                    det_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(maybe_det, det_dir, dirs_exist_ok=True)
                if maybe_rec.is_dir() and not rec_dir.is_dir():
                    rec_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(maybe_rec, rec_dir, dirs_exist_ok=True)
            except PermissionError:
                _emit(f"WARNING: could not copy from {base}; trying next candidate.")
                continue
            if det_dir.is_dir() and rec_dir.is_dir():
                break

    if not det_dir.is_dir() or not rec_dir.is_dir():
        cache = Path(r"D:\programming\caches\paddle\official_models")
        for name, dest in (
            (settings.ocr_detection_model_name, det_dir),
            (settings.ocr_recognition_model_name, rec_dir),
        ):
            src = cache / name
            if src.is_dir() and not dest.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                for path in src.rglob("*"):
                    rel = path.relative_to(src)
                    target = dest / rel
                    if path.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(path.read_bytes())

    if not det_dir.is_dir() or not rec_dir.is_dir():
        _emit(
            "ERROR: Model directories were not materialised under OCR_MODEL_ROOT. "
            "Re-run with network access or set PADDLE_PDX_MODEL_SOURCE=BOS."
        )
        return 1

    # Warm-up again from the local OCR_MODEL_ROOT (OneDNN disabled above).
    try:
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
            text_recognition_batch_size=settings.ocr_recognition_batch_size,
        )
        _ = ocr.predict(_synthetic_image())
    except Exception:
        _emit("ERROR: Warm-up inference failed against local model dirs.")
        traceback.print_exc()
        return 1

    import pypdfium2

    record = {
        "created_at": datetime.now(UTC).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "architecture": platform.architecture()[0],
        "paddlepaddle_version": getattr(paddle, "__version__", None),
        "paddleocr_version": getattr(paddleocr, "__version__", None),
        "pypdfium2_version": getattr(pypdfium2, "__version__", None),
        "detection_model_name": settings.ocr_detection_model_name,
        "recognition_model_name": settings.ocr_recognition_model_name,
        "detection_tree_hash": _tree_hash(det_dir),
        "recognition_tree_hash": _tree_hash(rec_dir),
        "device": settings.ocr_device,
        "engine": settings.ocr_engine,
        "handwriting_models_added": False,
        "vision_llm_added": False,
        "structure_models_added": False,
    }
    record_path = model_root / "model-record.json"
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _emit(f"Wrote {record_path.as_posix()}")
    _emit("OCR model bootstrap succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

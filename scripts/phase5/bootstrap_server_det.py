#!/usr/bin/env python3
"""Explicit offline bootstrap for PP-OCRv5_server_det (Phase 5 Task C1).

Does not replace the live Phase 4 mobile detector. Assets stay under the
gitignored OCR model root. Prefers an existing PaddleX/BOS cache copy; network
download is a fallback only when the cache is absent.

On Windows, avoids importing ``paddleocr`` (which pulls modelscope→torch) by
using the same modelscope stub path as ``paddle_adapter``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
import traceback
import types
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER_DET = "PP-OCRv5_server_det"


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


def _dir_size_bytes(directory: Path) -> int:
    total = 0
    for path in directory.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def _synthetic_image() -> object:
    import numpy as np
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (640, 160), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.text((24, 56), "VeriDemand server-det warm-up", fill=(0, 0, 0))
    return np.asarray(image)


def _cache_candidates() -> list[Path]:
    candidates: list[Path | None] = [
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
    return [c for c in candidates if c is not None]


def _materialise(det_dir: Path) -> bool:
    if det_dir.is_dir() and any(det_dir.iterdir()):
        return True
    for base in _cache_candidates():
        if not base.is_dir():
            continue
        maybe = base / SERVER_DET
        if not maybe.is_dir():
            continue
        try:
            det_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(maybe, det_dir, dirs_exist_ok=True)
            _emit(f"Copied {SERVER_DET} from {base.as_posix()}")
            return det_dir.is_dir() and any(det_dir.iterdir())
        except PermissionError:
            _emit(f"WARNING: could not copy from {base}; trying next candidate.")
    return False


def _import_paddlex_create_model():
    """Import paddlex.create_model with Windows Torch/modelscope stub retry."""

    def _load():
        from paddlex import create_model  # type: ignore[import-untyped]

        return create_model

    try:
        return _load()
    except (OSError, ImportError, ValueError) as first_exc:
        msg = str(first_exc).lower()
        if "shm.dll" not in msg and "torch" not in msg and "modelscope" not in msg:
            raise
        for name in list(sys.modules):
            if name == "paddlex" or name.startswith("paddlex.") or name == "modelscope":
                del sys.modules[name]
        if "modelscope" not in sys.modules:
            sys.modules["modelscope"] = types.ModuleType("modelscope")
        return _load()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-copy from cache even if the destination already exists.",
    )
    args = parser.parse_args(argv)

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    if platform.architecture()[0] != "64bit":
        _emit("ERROR: Python must be 64-bit for PaddlePaddle.")
        return 1

    from backend.app.settings.config import Settings

    settings = Settings()
    model_root = Path(settings.ocr_model_root)
    if not model_root.is_absolute():
        model_root = (ROOT / model_root).resolve()
    model_root.mkdir(parents=True, exist_ok=True)
    det_dir = model_root / SERVER_DET

    os.environ.setdefault(
        "PADDLE_PDX_MODEL_SOURCE", os.environ.get("PADDLE_PDX_MODEL_SOURCE", "BOS")
    )
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("FLAGS_onednn", "0")
    os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

    _emit(
        f"Bootstrapping shadow server detector {SERVER_DET} into {model_root.as_posix()} "
        f"(live mobile det remains {settings.ocr_detection_model_name})"
    )

    if args.force and det_dir.is_dir():
        shutil.rmtree(det_dir)

    if not _materialise(det_dir):
        _emit(
            "ERROR: Server detector was not found in local PaddleX caches and could "
            "not be materialised. Place PP-OCRv5_server_det under a cache candidate "
            "or enable network + BOS, then re-run."
        )
        return 1

    paddle_version = None
    paddlex_version = None
    try:
        import paddle

        paddle_version = getattr(paddle, "__version__", None)
        create_model = _import_paddlex_create_model()
        import paddlex

        paddlex_version = getattr(paddlex, "__version__", None)
        det = create_model(SERVER_DET, model_dir=str(det_dir))
        _ = det.predict(_synthetic_image())
    except Exception:
        _emit("ERROR: Warm-up inference failed against local server det dir.")
        traceback.print_exc()
        return 1

    record_path = model_root / "model-record.json"
    record: dict[str, object] = {}
    if record_path.is_file():
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            record = {}

    tree_hash = _tree_hash(det_dir)
    size_bytes = _dir_size_bytes(det_dir)
    shadow = {
        "model_name": SERVER_DET,
        "source": os.environ.get("PADDLE_PDX_MODEL_SOURCE", "BOS"),
        "resolved_path": det_dir.as_posix(),
        "tree_hash": tree_hash,
        "size_bytes": size_bytes,
        "licence": "Apache-2.0 (PaddleOCR / PaddlePaddle official model)",
        "provenance": "official PP-OCRv5 server detector via PaddleX/BOS cache",
        "bootstrap_command": "pnpm models:ocr:bootstrap:server-det",
        "live_detector_replaced": False,
        "bootstrapped_at": datetime.now(UTC).isoformat(),
        "paddlepaddle_version": paddle_version,
        "paddlex_version": paddlex_version,
        "platform": platform.platform(),
    }
    record["shadow_server_detector"] = shadow
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _emit(f"Wrote shadow record into {record_path.as_posix()}")
    _emit(
        json.dumps(
            {
                "model_name": SERVER_DET,
                "tree_hash": tree_hash,
                "size_bytes": size_bytes,
                "live_detector_unchanged": settings.ocr_detection_model_name,
            },
            indent=2,
        )
    )
    _emit("Server detector bootstrap succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

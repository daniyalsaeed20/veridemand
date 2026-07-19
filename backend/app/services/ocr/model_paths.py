"""OCR model cache paths outside the repository."""

from __future__ import annotations

import os
from pathlib import Path


def default_ocr_model_dir() -> Path:
    """Return the configured model-cache directory (outside the git repo)."""
    override = os.environ.get("VERIDEMAND_OCR_MODEL_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    local_app = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app:
        return Path(local_app) / "VeriDemand" / "paddleocr"

    xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
    if xdg:
        return Path(xdg).expanduser().resolve() / "veridemand" / "paddleocr"

    return Path.home() / ".cache" / "veridemand" / "paddleocr"


def ensure_ocr_model_dir() -> Path:
    path = default_ocr_model_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path

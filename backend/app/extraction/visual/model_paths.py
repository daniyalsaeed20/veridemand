"""Resolve OCR model paths against the repository root (not process cwd)."""

from __future__ import annotations

from pathlib import Path

# backend/app/extraction/visual/model_paths.py → repo root is parents[4]
_REPO_ROOT = Path(__file__).resolve().parents[4]


def repo_root() -> Path:
    """Return the VeriDemand repository root."""

    return _REPO_ROOT


def resolve_ocr_model_root(configured: Path | str) -> Path:
    """Resolve ``ocr_model_root`` to an absolute directory under the repo root.

    Relative paths are always resolved against the repository root so workers
    started with an explicit ``cwd`` and API processes started from another
    working directory share the same model tree.
    """

    path = Path(configured)
    path = (_REPO_ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    return path


def require_local_detection_dir(model_root: Path, *, detection_model_name: str) -> Path:
    """Return a local detection model dir or raise ``FileNotFoundError``."""

    det_dir = model_root / detection_model_name
    if not det_dir.is_dir() or not any(det_dir.iterdir()):
        raise FileNotFoundError(f"detection model directory missing or empty: {det_dir.name}")
    return det_dir


def require_local_model_dirs(
    model_root: Path,
    *,
    detection_model_name: str,
    recognition_model_name: str,
) -> tuple[Path, Path]:
    """Return detection/recognition dirs or raise ``FileNotFoundError``.

    Directories must exist and contain at least one file so PaddleOCR is not
    tempted to download into an empty placeholder folder.
    """

    det_dir = require_local_detection_dir(model_root, detection_model_name=detection_model_name)
    rec_dir = model_root / recognition_model_name
    if not rec_dir.is_dir() or not any(rec_dir.iterdir()):
        raise FileNotFoundError(f"recognition model directory missing or empty: {rec_dir.name}")
    return det_dir, rec_dir

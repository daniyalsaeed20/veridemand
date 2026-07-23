"""Unit tests for OCR model path resolution (no Paddle import)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.extraction.visual.model_paths import (
    repo_root,
    require_local_model_dirs,
    resolve_ocr_model_root,
)
from backend.app.settings.config import Settings


def test_resolve_relative_model_root_against_repo() -> None:
    resolved = resolve_ocr_model_root(".models/paddleocr")
    assert resolved.is_absolute()
    assert resolved == (repo_root() / ".models" / "paddleocr").resolve()


def test_settings_resolves_ocr_model_root(tmp_path: Path) -> None:
    settings = Settings(temp_root=tmp_path / "temp", ocr_enabled=False)
    assert settings.ocr_model_root.is_absolute()


def test_require_local_model_dirs_rejects_empty(tmp_path: Path) -> None:
    root = tmp_path / "models"
    det = root / "det"
    rec = root / "rec"
    det.mkdir(parents=True)
    rec.mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="empty"):
        require_local_model_dirs(root, detection_model_name="det", recognition_model_name="rec")


def test_require_local_model_dirs_ok(tmp_path: Path) -> None:
    root = tmp_path / "models"
    det = root / "det"
    rec = root / "rec"
    det.mkdir(parents=True)
    rec.mkdir(parents=True)
    (det / "inference.pdmodel").write_bytes(b"x")
    (rec / "inference.pdmodel").write_bytes(b"y")
    got_det, got_rec = require_local_model_dirs(
        root, detection_model_name="det", recognition_model_name="rec"
    )
    assert got_det == det
    assert got_rec == rec

"""Dependency-boundary tests for Phase 5 ONNX allowlists."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BOUNDARY = ROOT / "scripts" / "check_dependency_boundary.py"


def _load_boundary() -> Any:
    spec = importlib.util.spec_from_file_location("check_dependency_boundary", BOUNDARY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_boundary_script_passes_on_repo() -> None:
    module = _load_boundary()
    assert module.main() == 0


def test_onnxruntime_allowed_in_handwriting_router() -> None:
    module = _load_boundary()
    path = ROOT / "backend" / "app" / "extraction" / "handwriting_router" / "service.py"
    assert module._import_allowed(path, "onnxruntime") is True


def test_onnxruntime_forbidden_in_visual_worker() -> None:
    module = _load_boundary()
    path = ROOT / "backend" / "app" / "extraction" / "visual" / "worker.py"
    assert module._import_allowed(path, "onnxruntime") is False


def test_onnx_forbidden_in_health_service() -> None:
    module = _load_boundary()
    path = ROOT / "backend" / "app" / "health" / "service.py"
    assert module._import_allowed(path, "onnx") is False
    assert module._import_allowed(path, "onnxruntime") is False


def test_openai_and_cv2_remain_forbidden() -> None:
    module = _load_boundary()
    path = ROOT / "backend" / "app" / "extraction" / "handwriting_router" / "service.py"
    assert module._import_allowed(path, "openai") is False
    assert module._import_allowed(path, "cv2") is False
    assert module._import_allowed(path, "kraken") is False

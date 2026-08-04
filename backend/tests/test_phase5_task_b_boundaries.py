"""Phase 5 Task B boundary and non-wiring guards."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_torch_forbidden_in_backend_app() -> None:
    backend_app = ROOT / "backend" / "app"
    offenders: list[str] = []
    for path in backend_app.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in {"torch", "torchvision"}:
                        offenders.append(str(path.relative_to(ROOT)))
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.split(".")[0] in {"torch", "torchvision"}
            ):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_fastapi_does_not_import_model_development() -> None:
    main = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert "model_development" not in main
    offenders = []
    for path in (ROOT / "backend" / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "model_development" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_no_nist_emnist_or_unallowlisted_public_downloaders() -> None:
    """Task B2 permits explicit Handwritten ASAP prepare; NIST/EMNIST remain forbidden."""

    train_pkg = ROOT / "model_development" / "handwriting_classifier"
    for path in train_pkg.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "from openai" not in text
        assert "import cv2" not in text
        assert "import openai" not in text
        lower = text.lower()
        assert "emnist" not in lower
        assert "nist sd19" not in lower
        assert "special database 19" not in lower
        assert "download.pytorch.org/datasets" not in lower


def test_dependency_boundary_forbids_torch() -> None:
    script = (ROOT / "scripts" / "check_dependency_boundary.py").read_text(encoding="utf-8")
    assert '"torch"' in script
    assert '"torchvision"' in script


def test_router_still_disabled_by_default() -> None:
    from backend.app.settings.config import Settings

    s = Settings()
    assert s.handwriting_router_enabled is False
    assert s.handwriting_classifier_required is False


def test_check_dependency_boundary_script_runs() -> None:
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_dependency_boundary.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

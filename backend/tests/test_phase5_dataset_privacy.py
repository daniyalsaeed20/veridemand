"""Phase 5 dataset privacy + production boundary tests."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

from backend.app.main import app

ROOT = Path(__file__).resolve().parents[2]


def test_private_guard_allows_phase5_readme_only() -> None:
    guard = ROOT / "scripts" / "check_no_private_corpus.py"
    spec = importlib.util.spec_from_file_location("check_no_private_corpus", guard)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert (
        mod._violations(
            [
                "fixtures/private/phase5/README.example.md",
                "fixtures/private/.gitkeep",
            ]
        )
        == []
    )
    problems = mod._violations(
        [
            "fixtures/private/phase5/crops/crop_abc.png",
            "fixtures/private/phase5/manifests/crop-manifest.jsonl",
        ]
    )
    assert len(problems) == 2


def test_phase5_readme_example_is_tracked_allowlist() -> None:
    text = (ROOT / "scripts" / "check_no_private_corpus.py").read_text(encoding="utf-8")
    assert "fixtures/private/phase5/README.example.md" in text


def test_labeler_not_mounted_in_fastapi() -> None:
    paths = {getattr(r, "path", None) for r in app.routes}
    assert not any(p and "phase5" in p and "label" in p for p in paths if isinstance(p, str))
    # Soft check: no datasets.phase5 labeler import in main
    main_src = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert "labeler_server" not in main_src
    assert "handwriting_seed_server" not in main_src
    assert "coverage_server" not in main_src
    assert "datasets.phase5" not in main_src


def test_no_torch_openai_cv2_in_datasets_package() -> None:
    pkg = ROOT / "backend" / "app" / "datasets"
    banned = {"torch", "openai", "cv2", "sklearn", "label_studio", "streamlit"}
    for path in pkg.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in banned, path
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in banned, path


def test_task2_classifier_still_not_wired_into_worker() -> None:
    worker = (ROOT / "backend" / "app" / "extraction" / "visual" / "worker.py").read_text(
        encoding="utf-8"
    )
    repair = (ROOT / "backend" / "app" / "extraction" / "routing" / "repair_methods.py").read_text(
        encoding="utf-8"
    )
    assert "handwriting_router" not in worker
    assert "HandwritingClassifierService" not in worker
    assert "handwriting_router" not in repair
    assert "HandwritingClassifierService" not in repair

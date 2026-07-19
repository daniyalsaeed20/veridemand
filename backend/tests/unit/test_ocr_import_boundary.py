"""Architectural enforcement: only the OCR adapter may import paddle* packages."""

from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "app"
ALLOWED = {"services.ocr.adapter"}


def _module_name(path: Path) -> str:
    rel = path.relative_to(APP_ROOT).with_suffix("")
    return ".".join(rel.parts)


def _imports_paddle(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {"paddleocr", "paddle"} or alias.name.startswith(
                    ("paddleocr.", "paddle.")
                ):
                    return True
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module in {"paddleocr", "paddle"} or node.module.startswith(
                ("paddleocr.", "paddle.")
            ):
                return True
    return False


def test_only_ocr_adapter_imports_paddle() -> None:
    offenders: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        if not _imports_paddle(tree):
            continue
        name = _module_name(path)
        if name not in ALLOWED:
            offenders.append(name)
    assert offenders == [], f"paddle* imported outside OCR adapter: {offenders}"

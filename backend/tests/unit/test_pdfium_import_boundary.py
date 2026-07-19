"""Architectural enforcement: only pdfium_runtime may import pypdfium2."""

from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "app"
ALLOWED = {"services.documents.pdfium_runtime"}


def _module_name(path: Path) -> str:
    rel = path.relative_to(APP_ROOT).with_suffix("")
    return ".".join(rel.parts)


def _imports_pypdfium2(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pypdfium2" or alias.name.startswith("pypdfium2."):
                    return True
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "pypdfium2" or node.module.startswith("pypdfium2."):
                return True
    return False


def test_only_pdfium_runtime_imports_pypdfium2() -> None:
    offenders: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        if not _imports_pypdfium2(tree):
            continue
        name = _module_name(path)
        if name not in ALLOWED and not name.endswith(".pdfium_runtime"):
            offenders.append(name)
    assert offenders == [], f"pypdfium2 imported outside pdfium_runtime: {offenders}"

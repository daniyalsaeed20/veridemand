"""Unit tests for the private-corpus tracking guard (path checks only)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_GUARD = Path(__file__).resolve().parents[2] / "scripts" / "check_no_private_corpus.py"


def _load_violations() -> Any:
    spec = importlib.util.spec_from_file_location("check_no_private_corpus", _GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._violations


def test_allows_keep_and_readme_only_under_private() -> None:
    violations = _load_violations()
    tracked = [
        "fixtures/private/.gitkeep",
        "fixtures/private/README.example.md",
        "fixtures/private/visual-ocr-manifest.local.json.example",
        "fixtures/synthetic/uploads/valid.png",
        "docs/example/README.md",
    ]
    assert violations(tracked) == []


def test_rejects_tracked_document_under_docs_example() -> None:
    violations = _load_violations()
    problems = violations(["docs/example/case/sample.pdf"])
    assert len(problems) == 1
    assert "docs/example/" in problems[0]


def test_rejects_tracked_file_under_private_except_allowlist() -> None:
    violations = _load_violations()
    problems = violations(["fixtures/private/secret-scan.pdf"])
    assert len(problems) == 1
    assert "fixtures/private/" in problems[0]


def test_rejects_known_corpus_basename_outside_private() -> None:
    violations = _load_violations()
    problems = violations(["tmp/uploads/srmc-sj.pdf"])
    assert len(problems) == 1
    assert "outside fixtures/private" in problems[0]

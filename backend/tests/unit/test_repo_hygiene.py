"""Repo hygiene checks for Phase 0."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_gitignore_covers_temp_and_example_binaries() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "docs/example/*.pdf" in text
    assert "docs/example/*.docx" in text
    assert "data/sessions/" in text
    assert "tmp/" in text
    assert "spikes/**/out/" in text


def test_gitignore_covers_private_fixtures() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "fixtures/private/*" in text
    assert "!fixtures/private/README.example.md" in text


def test_only_example_readme_tracked_under_private_fixtures() -> None:
    result = subprocess.run(
        ["git", "ls-files", "fixtures/private"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    tracked = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert tracked == ["fixtures/private/README.example.md"]


def test_no_example_binaries_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "docs/example"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    tracked = [line for line in result.stdout.splitlines() if line.strip()]
    for path in tracked:
        assert not path.lower().endswith((".pdf", ".docx")), path


def test_no_spike_out_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "spikes"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    for path in result.stdout.splitlines():
        assert "/out/" not in path.replace("\\", "/")

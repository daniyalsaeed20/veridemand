"""Resolve private Phase 5 dataset root paths."""

from __future__ import annotations

from pathlib import Path

from backend.app.datasets.phase5.constants import (
    MANIFEST_FILES,
    PRIVATE_PHASE5_REL,
    PRIVATE_SUBDIRS,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


def default_private_root(repo_root: Path | None = None) -> Path:
    root = repo_root or REPO_ROOT
    return root / PRIVATE_PHASE5_REL


def ensure_layout(private_root: Path) -> None:
    for name in PRIVATE_SUBDIRS:
        (private_root / name).mkdir(parents=True, exist_ok=True)
    manifests = private_root / "manifests"
    for name in MANIFEST_FILES:
        path = manifests / name
        if not path.exists():
            path.write_text("", encoding="utf-8")


def manifest_path(private_root: Path, name: str) -> Path:
    return private_root / "manifests" / name


def crops_dir(private_root: Path) -> Path:
    return private_root / "crops"


def pages_dir(private_root: Path) -> Path:
    return private_root / "pages"


def reports_dir(private_root: Path) -> Path:
    return private_root / "reports"

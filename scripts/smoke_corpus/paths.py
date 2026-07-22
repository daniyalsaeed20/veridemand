"""Resolved paths for the committed synthetic smoke corpus."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_FIXTURE_DIR = REPO_ROOT / "fixtures" / "synthetic" / "smoke"
PDF_PATH = SMOKE_FIXTURE_DIR / "VeriDemand_Synthetic_PDF_Regression_Corpus_v1.0.pdf"
MANIFEST_PATH = SMOKE_FIXTURE_DIR / "VeriDemand_Synthetic_PDF_Regression_Manifest_v1.0.json"
README_PATH = REPO_ROOT / "docs" / "smoke" / "README.md"

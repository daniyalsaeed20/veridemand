"""Golden harness scaffold — metadata only."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.harness import GoldTestHarness

ROOT = Path(__file__).resolve().parents[3]


def test_load_gold_manifest_metadata_only() -> None:
    harness = GoldTestHarness(repo_root=ROOT)
    manifest = harness.load_gold_manifest()
    if not manifest.available:
        pytest.skip("docs/example/gold unavailable")
    assert any(e["kind"] == "gold_markdown" for e in manifest.entries)
    # Never assert on document body text; names/paths only.
    for entry in manifest.entries:
        assert "text" not in entry
        assert "content" not in entry

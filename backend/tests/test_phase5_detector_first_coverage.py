"""Handwriting-seed detector coverage classification."""

from __future__ import annotations

from backend.app.contracts.geometry import NormalisedBoundingBox
from backend.app.datasets.phase5.detector_first import classify_seed_coverage


def test_seed_exact_and_missed() -> None:
    seed = NormalisedBoundingBox(x=0.1, y=0.1, width=0.2, height=0.1)
    exact = NormalisedBoundingBox(x=0.1, y=0.1, width=0.2, height=0.1)
    assert classify_seed_coverage(seed, [exact]) in {"exact", "near_exact"}
    assert classify_seed_coverage(seed, []) == "missed"


def test_seed_contained_and_fragmented() -> None:
    seed = NormalisedBoundingBox(x=0.2, y=0.2, width=0.1, height=0.05)
    large = NormalisedBoundingBox(x=0.15, y=0.15, width=0.25, height=0.2)
    assert classify_seed_coverage(seed, [large]) == "contained"
    left = NormalisedBoundingBox(x=0.18, y=0.2, width=0.08, height=0.05)
    right = NormalisedBoundingBox(x=0.24, y=0.2, width=0.08, height=0.05)
    assert classify_seed_coverage(seed, [left, right]) == "fragmented"

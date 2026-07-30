"""Prove Task 2 did not wire the classifier into Phase 4 OCR paths."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_IMPORT_SNIPPETS = (
    "handwriting_router",
    "HandwritingClassifierService",
    "onnxruntime",
)


def test_visual_worker_does_not_import_classifier() -> None:
    text = (ROOT / "backend/app/extraction/visual/worker.py").read_text(encoding="utf-8")
    for snippet in FORBIDDEN_IMPORT_SNIPPETS:
        assert snippet not in text


def test_repair_methods_do_not_import_classifier() -> None:
    text = (ROOT / "backend/app/extraction/routing/repair_methods.py").read_text(encoding="utf-8")
    for snippet in FORBIDDEN_IMPORT_SNIPPETS:
        assert snippet not in text


def test_paddle_adapter_unchanged_combined_predict_surface() -> None:
    text = (ROOT / "backend/app/extraction/visual/paddle_adapter.py").read_text(encoding="utf-8")
    assert "def recognise(" in text
    assert "handwriting_router" not in text
    assert "onnxruntime" not in text


def test_progress_cap_still_65() -> None:
    from backend.app.contracts.documents import MAX_PHASE4_PROGRESS_PERCENT
    from backend.app.processing.progress_weights import OVERALL_CAP

    assert OVERALL_CAP == 65.0
    assert MAX_PHASE4_PROGRESS_PERCENT == 65

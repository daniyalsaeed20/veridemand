"""Phase 5 Task B3 dual-risk tests — retained as historical failure markers.

Active route-first coverage lives in ``test_phase5_task_b4_route_first.py``.
Task B3 could not simultaneously achieve zero handwriting leakage and
printed retention >= 80%; those reports/ADRs remain valid failed baselines.
"""

from __future__ import annotations

from model_development.handwriting_classifier import MODEL_VERSION, ROUTE_ORDER


def test_b3_superseded_by_route_first() -> None:
    assert ROUTE_ORDER == ("vision_required", "handwriting_present")
    assert "route-first" in MODEL_VERSION or "b4" in MODEL_VERSION

"""Phase 5 Task B3 ONNX tests — superseded by Task B4 route-first export tests.

See ``test_phase5_task_b4_onnx.py``.
"""

from __future__ import annotations

from model_development.handwriting_classifier.config import ONNX_OUTPUT_NAME


def test_b3_onnx_output_name_superseded() -> None:
    assert ONNX_OUTPUT_NAME == "route_logits"

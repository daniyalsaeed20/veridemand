"""Phase 5 Task B ONNX tests — superseded by Task B3 dual-risk suite.

Kept as a thin redirect so historical CI discovery stays green; full coverage
lives in ``test_phase5_task_b3_onnx.py``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("torch")
pytest.importorskip("onnx")
pytest.importorskip("onnxruntime")


def test_historical_three_class_onnx_superseded() -> None:
    """Task B three-class ONNX contract is superseded for safety evaluation."""

    import torch
    from model_development.handwriting_classifier.config import ONNX_OUTPUT_NAME
    from model_development.handwriting_classifier.model import build_model

    model = build_model(pretrained=False)
    y = model(torch.zeros(1, 3, 224, 224))
    assert ONNX_OUTPUT_NAME == "risk_logits"
    assert tuple(y.shape) == (1, 2)

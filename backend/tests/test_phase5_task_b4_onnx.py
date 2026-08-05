"""Phase 5 Task B4 ONNX export / parity tests (synthetic, no private crops)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("torch")
pytest.importorskip("onnx")
pytest.importorskip("onnxruntime")

from model_development.handwriting_classifier.config import (
    ONNX_INPUT_NAME,
    ONNX_OUTPUT_NAME,
    ThresholdCandidate,
)
from model_development.handwriting_classifier.export_onnx import (
    check_onnx,
    export_onnx,
    run_parity_suite,
)
from model_development.handwriting_classifier.model import build_model


def test_onnx_export_route_first_names_shapes(tmp_path: Path) -> None:
    model = build_model(pretrained=False)
    out = tmp_path / "model.onnx"
    export_onnx(model, out)
    check_onnx(out)

    import onnx

    m = onnx.load(str(out))
    assert m.graph.input[0].name == ONNX_INPUT_NAME
    assert m.graph.output[0].name == ONNX_OUTPUT_NAME
    assert ONNX_OUTPUT_NAME == "route_logits"
    dims = m.graph.input[0].type.tensor_type.shape.dim
    assert dims[0].dim_param == "batch"
    assert dims[1].dim_value == 3
    assert dims[2].dim_value == 224
    assert dims[3].dim_value == 224
    out_dims = m.graph.output[0].type.tensor_type.shape.dim
    assert out_dims[1].dim_value == 2


def test_pytorch_onnx_parity_and_routing(tmp_path: Path) -> None:
    model = build_model(pretrained=False)
    import torch

    with torch.no_grad():
        for p in model.parameters():
            p.add_(0.01)
    out = tmp_path / "model.onnx"
    export_onnx(model, out)
    thr = ThresholdCandidate(0.20, 0.70, 0.70)
    result = run_parity_suite(model, out, thresholds=thr)
    assert result["passed"], result
    assert result["output_name"] == "route_logits"
    assert result["route_order"] == ["vision_required", "handwriting_present"]
    assert result["output_semantics"] == "route_first_independent_logits"
    assert all(c["routed_outcome_agreement"] for c in result["cases"])
    assert all(c["output_dim"] == 2 for c in result["cases"])


def test_ort_cpu_session_smoke_route_first(tmp_path: Path) -> None:
    import onnxruntime as ort

    model = build_model(pretrained=False)
    out = tmp_path / "model.onnx"
    export_onnx(model, out)
    sess = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    x = np.zeros((1, 3, 224, 224), dtype=np.float32)
    y = sess.run([ONNX_OUTPUT_NAME], {ONNX_INPUT_NAME: x})[0]
    assert y.shape == (1, 2)
    assert np.all(np.isfinite(y))
    x2 = np.zeros((4, 3, 224, 224), dtype=np.float32)
    y2 = sess.run([ONNX_OUTPUT_NAME], {ONNX_INPUT_NAME: x2})[0]
    assert y2.shape == (4, 2)


def test_runtime_preprocess_feeds_onnx(tmp_path: Path) -> None:
    from model_development.handwriting_classifier.transforms import runtime_preprocess

    model = build_model(pretrained=False)
    out = tmp_path / "model.onnx"
    export_onnx(model, out)
    import onnxruntime as ort

    sess = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    img = Image.new("RGB", (100, 40), color=(200, 200, 200))
    batch = runtime_preprocess(img)
    y = sess.run([ONNX_OUTPUT_NAME], {ONNX_INPUT_NAME: batch})[0]
    assert y.shape == (1, 2)

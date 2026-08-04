"""Phase 5 Task B ONNX export / parity tests (synthetic, no private crops)."""

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


def test_onnx_export_names_shapes_dynamic_batch(tmp_path: Path) -> None:
    model = build_model(pretrained=False)
    out = tmp_path / "model.onnx"
    export_onnx(model, out)
    check_onnx(out)

    import onnx

    m = onnx.load(str(out))
    assert m.graph.input[0].name == ONNX_INPUT_NAME
    assert m.graph.output[0].name == ONNX_OUTPUT_NAME
    # dynamic batch: dim_param present on batch axis
    dims = m.graph.input[0].type.tensor_type.shape.dim
    assert dims[0].dim_param == "batch"
    assert dims[1].dim_value == 3
    assert dims[2].dim_value == 224
    assert dims[3].dim_value == 224
    out_dims = m.graph.output[0].type.tensor_type.shape.dim
    assert out_dims[1].dim_value == 3


def test_pytorch_onnx_parity_argmax_and_routing(tmp_path: Path) -> None:
    model = build_model(pretrained=False)
    # randomize head a bit for non-zero outputs
    import torch

    with torch.no_grad():
        for p in model.parameters():
            p.add_(0.01)
    out = tmp_path / "model.onnx"
    export_onnx(model, out)
    thr = ThresholdCandidate(0.5, 0.5, 0.5, 0.05)
    result = run_parity_suite(model, out, thresholds=thr)
    assert result["passed"], result
    assert result["max_abs_diff"] <= 1e-4 or result["cases"][0]["argmax_agreement"]
    assert all(c["argmax_agreement"] for c in result["cases"])
    assert all(c["routed_outcome_agreement"] for c in result["cases"])


def test_ort_cpu_session_smoke(tmp_path: Path) -> None:
    import onnxruntime as ort

    model = build_model(pretrained=False)
    out = tmp_path / "model.onnx"
    export_onnx(model, out)
    sess = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    x = np.zeros((1, 3, 224, 224), dtype=np.float32)
    y = sess.run([ONNX_OUTPUT_NAME], {ONNX_INPUT_NAME: x})[0]
    assert y.shape == (1, 3)
    assert np.all(np.isfinite(y))
    # multi-batch
    x2 = np.zeros((4, 3, 224, 224), dtype=np.float32)
    y2 = sess.run([ONNX_OUTPUT_NAME], {ONNX_INPUT_NAME: x2})[0]
    assert y2.shape == (4, 3)


def test_varied_crop_shapes_preprocess(tmp_path: Path) -> None:
    from model_development.handwriting_classifier.transforms import runtime_preprocess

    for shape in ((32, 32), (20, 200), (150, 40)):
        img = Image.new(
            "RGB", shape[::-1] if False else (shape[1], shape[0]), color=(240, 240, 240)
        )
        # shape is (h,w) — PIL wants (w,h)
        img = Image.new("RGB", (shape[1], shape[0]), color=(240, 240, 240))
        t = runtime_preprocess(img)
        assert t.shape == (1, 3, 224, 224)

"""ONNX export and PyTorch↔ORT parity checks."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from model_development.handwriting_classifier.config import (
    CLASS_ORDER,
    INPUT_SIZE,
    ONNX_INPUT_NAME,
    ONNX_OPSET,
    ONNX_OUTPUT_NAME,
    PARITY_TOLERANCE,
    ThresholdCandidate,
)
from model_development.handwriting_classifier.thresholds import route_probabilities
from model_development.handwriting_classifier.transforms import runtime_preprocess


def export_onnx(model: Any, out_path: Path, *, opset: int = ONNX_OPSET) -> Path:
    import torch

    out_path.parent.mkdir(parents=True, exist_ok=True)
    model = model.cpu().eval()
    dummy = torch.zeros(1, 3, INPUT_SIZE, INPUT_SIZE, dtype=torch.float32)
    torch.onnx.export(
        model,
        dummy,
        str(out_path),
        input_names=[ONNX_INPUT_NAME],
        output_names=[ONNX_OUTPUT_NAME],
        dynamic_axes={
            ONNX_INPUT_NAME: {0: "batch"},
            ONNX_OUTPUT_NAME: {0: "batch"},
        },
        opset_version=opset,
        do_constant_folding=True,
    )
    return out_path


def check_onnx(path: Path) -> None:
    import onnx
    from onnx import checker

    model = onnx.load(str(path))
    checker.check_model(model)
    # Basic shape expectations
    inputs = model.graph.input
    outputs = model.graph.output
    assert len(inputs) == 1 and inputs[0].name == ONNX_INPUT_NAME
    assert len(outputs) == 1 and outputs[0].name == ONNX_OUTPUT_NAME


def _ort_session(path: Path) -> Any:
    import onnxruntime as ort

    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def pytorch_logits(model: Any, batch: np.ndarray, device: str = "cpu") -> np.ndarray:
    import torch

    model = model.to(device).eval()
    with torch.no_grad():
        t = torch.from_numpy(batch).to(device)
        return model(t).detach().cpu().numpy().astype(np.float64)


def ort_logits(session: Any, batch: np.ndarray) -> np.ndarray:
    out = session.run([ONNX_OUTPUT_NAME], {ONNX_INPUT_NAME: batch.astype(np.float32)})[0]
    return np.asarray(out, dtype=np.float64)


def compare_parity(
    torch_out: np.ndarray,
    ort_out: np.ndarray,
    *,
    thresholds: ThresholdCandidate | None = None,
    tol: float = PARITY_TOLERANCE,
) -> dict[str, Any]:
    abs_diff = np.max(np.abs(torch_out - ort_out))
    rel = np.max(np.abs(torch_out - ort_out) / np.maximum(np.abs(torch_out), 1e-8))
    argmax_agree = bool(np.all(np.argmax(torch_out, axis=1) == np.argmax(ort_out, axis=1)))
    routed_agree = True
    if thresholds is not None:
        for i in range(torch_out.shape[0]):
            # Convert logits → probs for routing
            def _softmax(x: np.ndarray) -> np.ndarray:
                e = np.exp(x - np.max(x))
                return e / e.sum()

            t_route = route_probabilities(_softmax(torch_out[i]), thresholds)
            o_route = route_probabilities(_softmax(ort_out[i]), thresholds)
            if t_route != o_route:
                routed_agree = False
                break
    return {
        "max_abs_diff": float(abs_diff),
        "max_rel_diff": float(rel),
        "argmax_agreement": argmax_agree,
        "routed_outcome_agreement": routed_agree,
        "within_tolerance": bool(abs_diff <= tol),
        "tolerance": tol,
    }


def run_parity_suite(
    model: Any,
    onnx_path: Path,
    *,
    sample_images: Sequence[Any] | None = None,
    thresholds: ThresholdCandidate | None = None,
    tol: float = PARITY_TOLERANCE,
) -> dict[str, Any]:
    """Compare Torch vs ORT on synthetic + optional private samples."""

    from PIL import Image

    check_onnx(onnx_path)
    session = _ort_session(onnx_path)

    cases: list[tuple[str, np.ndarray]] = []
    # Deterministic synthetic fixtures with varied shapes before preprocess
    rng = np.random.default_rng(0)
    for name, shape in (
        ("synth_square", (64, 64)),
        ("synth_wide", (40, 200)),
        ("synth_tall", (180, 50)),
        ("synth_small", (24, 24)),
    ):
        arr = rng.integers(0, 255, size=(*shape, 3), dtype=np.uint8)
        img = Image.fromarray(arr)
        cases.append((name, runtime_preprocess(img)))

    if sample_images:
        for i, img in enumerate(sample_images):
            cases.append((f"private_sample_{i}", runtime_preprocess(img)))

    results = []
    all_ok = True
    # batch size 1
    for name, tensor in cases:
        torch_out = pytorch_logits(model, tensor)
        ort_out = ort_logits(session, tensor)
        cmp = compare_parity(torch_out, ort_out, thresholds=thresholds, tol=tol)
        cmp["case"] = name
        cmp["batch_size"] = 1
        results.append(cmp)
        if not (cmp["argmax_agreement"] and cmp["routed_outcome_agreement"]):
            all_ok = False

    # multi-item batch
    batch = np.concatenate([t for _, t in cases[:3]], axis=0)
    torch_out = pytorch_logits(model, batch)
    ort_out = ort_logits(session, batch)
    cmp = compare_parity(torch_out, ort_out, thresholds=thresholds, tol=tol)
    cmp["case"] = "batch3"
    cmp["batch_size"] = 3
    results.append(cmp)
    if not (cmp["argmax_agreement"] and cmp["routed_outcome_agreement"]):
        all_ok = False

    max_abs = max(r["max_abs_diff"] for r in results)
    return {
        "passed": all_ok and max_abs <= tol,
        "max_abs_diff": max_abs,
        "cases": results,
        "opset": ONNX_OPSET,
        "input_name": ONNX_INPUT_NAME,
        "output_name": ONNX_OUTPUT_NAME,
        "class_order": list(CLASS_ORDER),
    }

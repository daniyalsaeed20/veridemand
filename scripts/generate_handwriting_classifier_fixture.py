#!/usr/bin/env python3
"""Generate a tiny deterministic ONNX test fixture for the handwriting classifier.

Requires the ``model-dev`` dependency group (``onnx``). Produces a test_fixture
package under ``backend/tests/fixtures/handwriting_classifier/`` — never a
production model.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "backend" / "tests" / "fixtures" / "handwriting_classifier"


def _build_logits_model(path: Path, *, input_name: str, output_name: str, size: int) -> None:
    import numpy as np
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    # y = x.mean(over spatial) @ W + b  → shape [N, 3]
    # Implement as ReduceMean + MatMul + Add for a tiny graph.
    n_in = helper.make_tensor_value_info(input_name, TensorProto.FLOAT, ["N", 3, size, size])
    n_out = helper.make_tensor_value_info(output_name, TensorProto.FLOAT, ["N", 3])

    # Flatten spatial via GlobalAveragePool → [N,3,1,1] then Squeeze → [N,3]
    gap = helper.make_node("GlobalAveragePool", [input_name], ["gap"])
    squeeze = helper.make_node("Squeeze", ["gap", "axes"], ["pooled"])
    axes = numpy_helper.from_array(np.asarray([2, 3], dtype=np.int64), name="axes")
    # Identity weight so pooled features pass through; bias steers class preference.
    w = numpy_helper.from_array(np.eye(3, dtype=np.float32), name="W")
    b = numpy_helper.from_array(
        np.asarray([2.0, 0.0, 0.0], dtype=np.float32), name="B"
    )  # prefers printed logits
    matmul = helper.make_node("MatMul", ["pooled", "W"], ["proj"])
    add = helper.make_node("Add", ["proj", "B"], [output_name])

    graph = helper.make_graph(
        [gap, squeeze, matmul, add],
        "handwriting_logits_fixture",
        [n_in],
        [n_out],
        [axes, w, b],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    onnx.save(model, str(path))


def main() -> int:
    try:
        import onnx  # noqa: F401
    except ImportError:
        print("ERROR: install model-dev group: uv sync --group model-dev", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    model_path = OUT / "model.onnx"
    size = 32
    _build_logits_model(model_path, input_name="input", output_name="logits", size=size)
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()

    labels = ["printed", "handwritten", "non_text"]
    (OUT / "labels.json").write_text(json.dumps(labels, indent=2) + "\n", encoding="utf-8")

    record = {
        "schema_version": "phase5-handwriting-classifier-v1",
        "model_family": "handwriting_style_cnn",
        "model_version": "test-fixture-logits-v1",
        "release_status": "test_fixture",
        "training_code_version": "task2-fixture-generator",
        "onnx_opset": 13,
        "onnx_ir_version": 8,
        "input_tensor_name": "input",
        "input_dtype": "float32",
        "input_shape": [None, 3, size, size],
        "dynamic_batch": True,
        "colour_mode": "rgb",
        "channel_order": "nchw",
        "target_width": size,
        "target_height": size,
        "resize_policy": "letterbox",
        "aspect_ratio_policy": "preserve",
        "padding_policy": "constant",
        "padding_value": 0.0,
        "interpolation": "bilinear",
        "normalisation_mean": [0.5, 0.5, 0.5],
        "normalisation_std": [0.5, 0.5, 0.5],
        "output_tensor_name": "logits",
        "output_dtype": "float32",
        "output_semantics": "logits",
        "class_order": labels,
        "threshold_set_version": "provisional-unspecified",
        "training_manifest_sha256": None,
        "validation_manifest_sha256": None,
        "held_out_manifest_sha256": None,
        "model_sha256": digest,
        "pretrained_weight_provenance": "synthetic-identity-fixture",
        "model_provenance": "scripts/generate_handwriting_classifier_fixture.py",
        "licence": "Proprietary-test-fixture",
        "created_at": datetime.now(UTC).isoformat(),
        "supported_onnxruntime_version": ">=1.19,<2",
        "expected_execution_provider": "CPUExecutionProvider",
        "notes": "Deterministic Task 2 unit-test fixture. Not for production.",
    }
    (OUT / "model-record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    metrics = {
        "schema_version": "phase5-handwriting-metrics-v1",
        "metrics_kind": "synthetic_test",
        "model_version": "test-fixture-logits-v1",
        "notes": "No evaluation claims. Synthetic smoke only.",
        "handwriting_safe_bypass_recall": None,
        "handwriting_to_paddle_leak_count": None,
        "class_support": None,
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Handwriting classifier test fixture\n\n"
        "Generated by `scripts/generate_handwriting_classifier_fixture.py`.\n"
        f"model SHA-256: `{digest}`\n"
        "Status: `test_fixture` — must not satisfy production-required readiness.\n",
        encoding="utf-8",
    )
    print(f"Wrote fixture package to {OUT.as_posix()}")
    print(f"model_sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

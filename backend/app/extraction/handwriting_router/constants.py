"""Shared constants for the Phase 5 handwriting classifier package."""

from __future__ import annotations

EXPECTED_MODEL_LABELS: tuple[str, str, str] = ("printed", "handwritten", "non_text")
MODEL_ONNX_NAME = "model.onnx"
LABELS_JSON_NAME = "labels.json"
MODEL_RECORD_NAME = "model-record.json"
METRICS_JSON_NAME = "metrics.json"
CPU_EXECUTION_PROVIDER = "CPUExecutionProvider"
PROBABILITY_SUM_TOLERANCE = 1e-3
MAX_INPUT_PIXELS = 4_000_000

"""Shared constants for the Phase 5 handwriting classifier package."""

from __future__ import annotations

# Route-first ONNX outputs (Task B4). Not public routing outcomes.
EXPECTED_ROUTE_OUTPUTS: tuple[str, str] = ("vision_required", "handwriting_present")
# Historical dual-risk ONNX outputs (Task B3 fixtures / baselines only).
EXPECTED_RISK_OUTPUTS: tuple[str, str] = ("handwriting_risk", "non_text_risk")
PUBLIC_ROUTING_OUTCOMES: tuple[str, str, str, str] = (
    "printed",
    "handwritten",
    "uncertain",
    "non_text",
)
# Historical three-class package labels (Task 2 / B / B2 fixtures only).
HISTORICAL_THREE_CLASS_LABELS: tuple[str, str, str] = ("printed", "handwritten", "non_text")
# Primary production expectation is route-first.
EXPECTED_MODEL_LABELS: tuple[str, str] = EXPECTED_ROUTE_OUTPUTS

MODEL_ONNX_NAME = "model.onnx"
LABELS_JSON_NAME = "labels.json"
MODEL_RECORD_NAME = "model-record.json"
METRICS_JSON_NAME = "metrics.json"
CPU_EXECUTION_PROVIDER = "CPUExecutionProvider"
PROBABILITY_SUM_TOLERANCE = 1e-3
MAX_INPUT_PIXELS = 4_000_000
SCHEMA_VERSION_V1 = "phase5-handwriting-classifier-v1"
SCHEMA_VERSION_V2 = "phase5-handwriting-classifier-v2"
SCHEMA_VERSION_V3 = "phase5-handwriting-classifier-v3"

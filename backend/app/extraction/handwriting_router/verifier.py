"""Model-package verification for the Phase 5 handwriting classifier."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
from backend.app.extraction.handwriting_router.constants import (
    CPU_EXECUTION_PROVIDER,
    EXPECTED_RISK_OUTPUTS,
    EXPECTED_ROUTE_OUTPUTS,
    HISTORICAL_THREE_CLASS_LABELS,
    LABELS_JSON_NAME,
    METRICS_JSON_NAME,
    MODEL_ONNX_NAME,
    MODEL_RECORD_NAME,
    PUBLIC_ROUTING_OUTCOMES,
    SCHEMA_VERSION_V1,
    SCHEMA_VERSION_V2,
    SCHEMA_VERSION_V3,
)
from backend.app.extraction.handwriting_router.manifest import (
    ClassifierPackageStatus,
    HandwritingMetricsRecord,
    HandwritingModelRecord,
    OutputSemantics,
)


class VerificationFailureCode(StrEnum):
    PACKAGE_DIR_MISSING = "package_dir_missing"
    FILE_MISSING = "file_missing"
    NOT_REGULAR_FILE = "not_regular_file"
    MANIFEST_INVALID = "manifest_invalid"
    LABELS_INVALID = "labels_invalid"
    METRICS_INVALID = "metrics_invalid"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    ONNX_STRUCTURAL_INVALID = "onnx_structural_invalid"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    SESSION_INIT_FAILED = "session_init_failed"
    INPUT_MISMATCH = "input_mismatch"
    OUTPUT_MISMATCH = "output_mismatch"
    SMOKE_FAILED = "smoke_failed"
    TEST_FIXTURE_NOT_ALLOWED = "test_fixture_not_allowed"


@dataclass(frozen=True, slots=True)
class PackageVerificationResult:
    ready: bool
    model_version: str | None
    threshold_set_version: str | None
    package_status: ClassifierPackageStatus | None
    checksum_ok: bool | None
    runtime_provider: str | None
    failure_code: VerificationFailureCode | None
    message: str
    record: HandwritingModelRecord | None = None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _fail(
    code: VerificationFailureCode,
    message: str,
    *,
    record: HandwritingModelRecord | None = None,
    checksum_ok: bool | None = None,
) -> PackageVerificationResult:
    return PackageVerificationResult(
        ready=False,
        model_version=record.model_version if record else None,
        threshold_set_version=record.threshold_set_version if record else None,
        package_status=record.release_status if record else None,
        checksum_ok=checksum_ok,
        runtime_provider=None,
        failure_code=code,
        message=message,
        record=record,
    )


def _load_labels(path: Path) -> dict[str, Any] | list[str] | PackageVerificationResult:
    """Accept v1 string-array, v2 dual-risk, or v3 route-first labels."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _fail(VerificationFailureCode.LABELS_INVALID, "labels.json could not be parsed.")

    # Structured v2 / v3
    if isinstance(raw, dict):
        semantics = raw.get("output_semantics")
        outputs = raw.get("outputs")
        public = raw.get("public_outcomes")
        if semantics == OutputSemantics.ROUTE_FIRST_INDEPENDENT_LOGITS.value:
            if outputs != list(EXPECTED_ROUTE_OUTPUTS):
                return _fail(
                    VerificationFailureCode.LABELS_INVALID,
                    "v3 labels.json outputs must be [vision_required, handwriting_present].",
                )
        elif semantics == OutputSemantics.INDEPENDENT_BINARY_RISK_LOGITS.value:
            if outputs != list(EXPECTED_RISK_OUTPUTS):
                return _fail(
                    VerificationFailureCode.LABELS_INVALID,
                    "v2 labels.json outputs must be [handwriting_risk, non_text_risk].",
                )
        else:
            return _fail(
                VerificationFailureCode.LABELS_INVALID,
                "structured labels.json must declare route_first_independent_logits "
                "or independent_binary_risk_logits.",
            )
        if public != list(PUBLIC_ROUTING_OUTCOMES):
            return _fail(
                VerificationFailureCode.LABELS_INVALID,
                "labels.json public_outcomes must match the four routing outcomes.",
            )
        if "uncertain" in (outputs or []):
            return _fail(
                VerificationFailureCode.LABELS_INVALID,
                "uncertain must not appear as a model output class.",
            )
        return raw

    # v1 historical array
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        return _fail(VerificationFailureCode.LABELS_INVALID, "labels.json must be a string array.")
    if raw != list(HISTORICAL_THREE_CLASS_LABELS):
        return _fail(
            VerificationFailureCode.LABELS_INVALID,
            "labels.json must exactly match [printed, handwritten, non_text] for v1.",
        )
    if len(set(raw)) != len(raw):
        return _fail(VerificationFailureCode.LABELS_INVALID, "labels.json contains duplicates.")
    if "uncertain" in raw:
        return _fail(
            VerificationFailureCode.LABELS_INVALID,
            "uncertain must not appear as a model class.",
        )
    return raw


def package_directory_from_path(configured: Path) -> Path:
    """Accept either the package directory or a path to model.onnx."""

    if configured.suffix.lower() == ".onnx":
        return configured.parent
    return configured


def verify_classifier_package(
    package_dir: Path,
    *,
    allow_test_fixture: bool = False,
    run_onnx_checker: bool = True,
    run_runtime_smoke: bool = True,
) -> PackageVerificationResult:
    """Validate a classifier package. Never includes absolute paths in messages."""

    root = package_directory_from_path(package_dir)
    if not root.is_dir():
        return _fail(
            VerificationFailureCode.PACKAGE_DIR_MISSING,
            "Classifier package directory is missing.",
        )

    required = {
        MODEL_ONNX_NAME: root / MODEL_ONNX_NAME,
        LABELS_JSON_NAME: root / LABELS_JSON_NAME,
        MODEL_RECORD_NAME: root / MODEL_RECORD_NAME,
        METRICS_JSON_NAME: root / METRICS_JSON_NAME,
    }
    for name, path in required.items():
        if not path.exists():
            return _fail(
                VerificationFailureCode.FILE_MISSING,
                f"Required package file missing: {name}.",
            )
        if not path.is_file():
            return _fail(
                VerificationFailureCode.NOT_REGULAR_FILE,
                f"Required package path is not a regular file: {name}.",
            )

    labels_result = _load_labels(required[LABELS_JSON_NAME])
    if isinstance(labels_result, PackageVerificationResult):
        return labels_result

    try:
        record = HandwritingModelRecord.model_validate_json(
            required[MODEL_RECORD_NAME].read_text(encoding="utf-8")
        )
    except Exception as exc:
        return _fail(
            VerificationFailureCode.MANIFEST_INVALID,
            f"model-record.json invalid: {type(exc).__name__}.",
        )

    # Cross-check labels vs record schema.
    if record.schema_version in {SCHEMA_VERSION_V2, SCHEMA_VERSION_V3}:
        if not isinstance(labels_result, dict):
            return _fail(
                VerificationFailureCode.LABELS_INVALID,
                "v2/v3 packages require structured labels.json.",
                record=record,
            )
    elif record.schema_version == SCHEMA_VERSION_V1 and not isinstance(labels_result, list):
        return _fail(
            VerificationFailureCode.LABELS_INVALID,
            "v1 packages require array labels.json.",
            record=record,
        )

    try:
        HandwritingMetricsRecord.model_validate_json(
            required[METRICS_JSON_NAME].read_text(encoding="utf-8")
        )
    except Exception as exc:
        return _fail(
            VerificationFailureCode.METRICS_INVALID,
            f"metrics.json invalid: {type(exc).__name__}.",
            record=record,
        )

    if record.release_status is ClassifierPackageStatus.TEST_FIXTURE and not allow_test_fixture:
        return _fail(
            VerificationFailureCode.TEST_FIXTURE_NOT_ALLOWED,
            "test_fixture packages cannot satisfy production-required readiness.",
            record=record,
        )

    digest = _sha256_file(required[MODEL_ONNX_NAME])
    if digest != record.model_sha256:
        return _fail(
            VerificationFailureCode.CHECKSUM_MISMATCH,
            "model.onnx SHA-256 does not match model-record.json.",
            record=record,
            checksum_ok=False,
        )

    if run_onnx_checker:
        try:
            import onnx

            model = onnx.load(str(required[MODEL_ONNX_NAME]))
            onnx.checker.check_model(model)
        except ImportError:
            pass
        except Exception as exc:
            return _fail(
                VerificationFailureCode.ONNX_STRUCTURAL_INVALID,
                f"ONNX structural validation failed: {type(exc).__name__}.",
                record=record,
                checksum_ok=True,
            )

    if not run_runtime_smoke:
        return PackageVerificationResult(
            ready=True,
            model_version=record.model_version,
            threshold_set_version=record.threshold_set_version,
            package_status=record.release_status,
            checksum_ok=True,
            runtime_provider=CPU_EXECUTION_PROVIDER,
            failure_code=None,
            message="Package static validation passed.",
            record=record,
        )

    try:
        import onnxruntime as ort
    except ImportError:
        return _fail(
            VerificationFailureCode.RUNTIME_UNAVAILABLE,
            "onnxruntime is not importable.",
            record=record,
            checksum_ok=True,
        )

    available = set(ort.get_available_providers())
    if CPU_EXECUTION_PROVIDER not in available:
        return _fail(
            VerificationFailureCode.PROVIDER_UNAVAILABLE,
            "CPUExecutionProvider is unavailable.",
            record=record,
            checksum_ok=True,
        )

    try:
        session = ort.InferenceSession(
            str(required[MODEL_ONNX_NAME]),
            providers=[CPU_EXECUTION_PROVIDER],
        )
    except Exception as exc:
        return _fail(
            VerificationFailureCode.SESSION_INIT_FAILED,
            f"ONNX Runtime session initialisation failed: {type(exc).__name__}.",
            record=record,
            checksum_ok=True,
        )

    inputs = session.get_inputs()
    outputs = session.get_outputs()
    if not inputs or inputs[0].name != record.input_tensor_name:
        return _fail(
            VerificationFailureCode.INPUT_MISMATCH,
            "ONNX input tensor name does not match the manifest.",
            record=record,
            checksum_ok=True,
        )
    if not outputs or outputs[0].name != record.output_tensor_name:
        return _fail(
            VerificationFailureCode.OUTPUT_MISMATCH,
            "ONNX output tensor name does not match the manifest.",
            record=record,
            checksum_ok=True,
        )

    if record.channel_order.value == "nchw":
        shape = (1, len(record.normalisation_mean), record.target_height, record.target_width)
    else:
        shape = (1, record.target_height, record.target_width, len(record.normalisation_mean))
    feed = {record.input_tensor_name: np.zeros(shape, dtype=np.float32)}
    try:
        raw_out: list[Any] = session.run([record.output_tensor_name], feed)
    except Exception as exc:
        return _fail(
            VerificationFailureCode.SMOKE_FAILED,
            f"Synthetic inference smoke failed: {type(exc).__name__}.",
            record=record,
            checksum_ok=True,
        )
    if not raw_out:
        return _fail(
            VerificationFailureCode.SMOKE_FAILED,
            "Synthetic inference returned empty output.",
            record=record,
            checksum_ok=True,
        )
    out = np.asarray(raw_out[0], dtype=np.float64)
    expected_dim = record.expected_output_dim
    if out.ndim != 2 or out.shape[0] != 1 or out.shape[1] != expected_dim:
        return _fail(
            VerificationFailureCode.OUTPUT_MISMATCH,
            f"Smoke output shape must be [1, {expected_dim}].",
            record=record,
            checksum_ok=True,
        )
    if not np.all(np.isfinite(out)):
        return _fail(
            VerificationFailureCode.SMOKE_FAILED,
            "Smoke output contained non-finite values.",
            record=record,
            checksum_ok=True,
        )
    if record.output_semantics is OutputSemantics.PROBABILITIES:
        row = out[0]
        if np.any(row < -1e-6) or abs(float(row.sum()) - 1.0) > 0.05:
            return _fail(
                VerificationFailureCode.SMOKE_FAILED,
                "Probability smoke output failed basic validity checks.",
                record=record,
                checksum_ok=True,
            )

    return PackageVerificationResult(
        ready=True,
        model_version=record.model_version,
        threshold_set_version=record.threshold_set_version,
        package_status=record.release_status,
        checksum_ok=True,
        runtime_provider=CPU_EXECUTION_PROVIDER,
        failure_code=None,
        message="Classifier package verified.",
        record=record,
    )

"""Write verified route-first runtime model package under models/handwriting_classifier/."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from backend.app.extraction.handwriting_router.constants import (
    EXPECTED_ROUTE_OUTPUTS,
    PUBLIC_ROUTING_OUTCOMES,
    SCHEMA_VERSION_V3,
)
from backend.app.extraction.handwriting_router.manifest import (
    ClassifierPackageStatus,
    HandwritingMetricsRecord,
    HandwritingModelRecord,
    MetricsKind,
    OutputSemantics,
)
from backend.app.extraction.handwriting_router.verifier import verify_classifier_package

from model_development.handwriting_classifier import THRESHOLD_SET_VERSION
from model_development.handwriting_classifier.config import (
    INPUT_SIZE,
    ONNX_INPUT_NAME,
    ONNX_OPSET,
    ONNX_OUTPUT_NAME,
    RuntimePreprocessSpec,
)
from model_development.handwriting_classifier.thresholds import ThresholdMetrics, thresholds_to_dict


def file_sha256(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_package(
    package_dir: Path,
    onnx_path: Path,
    model_version: str,
    training_code_version: str,
    release_status: ClassifierPackageStatus,
    training_manifest_sha256: str,
    validation_manifest_sha256: str,
    held_out_manifest_sha256: str,
    threshold_metrics: ThresholdMetrics,
    oof_summary: dict[str, Any],
    label_aggregates: dict[str, int],
    synthetic_nontext_count: int,
    training_config_hash: str,
    pretrained_provenance: str,
    torch_version: str,
    torchvision_version: str,
    onnx_version: str,
    onnxruntime_version: str,
    notes: str,
    preprocess: RuntimePreprocessSpec | None = None,
    public_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create route-first package files and run the production verifier."""

    package_dir.mkdir(parents=True, exist_ok=True)
    dest_onnx = package_dir / "model.onnx"
    dest_onnx.write_bytes(onnx_path.read_bytes())
    model_digest = file_sha256(dest_onnx)

    labels_payload = {
        "output_semantics": OutputSemantics.ROUTE_FIRST_INDEPENDENT_LOGITS.value,
        "outputs": list(EXPECTED_ROUTE_OUTPUTS),
        "public_outcomes": list(PUBLIC_ROUTING_OUTCOMES),
    }
    (package_dir / "labels.json").write_text(
        json.dumps(labels_payload, indent=2) + "\n",
        encoding="utf-8",
    )

    spec = preprocess or RuntimePreprocessSpec()
    thr_note = thresholds_to_dict(threshold_metrics)
    pub = public_provenance or {}
    notes_full = (
        f"{notes}\n"
        f"thresholds={json.dumps(thr_note, sort_keys=True)}; "
        f"training_config_hash={training_config_hash}; "
        f"label_aggregates={json.dumps(label_aggregates, sort_keys=True)}; "
        f"synthetic_nontext_count={synthetic_nontext_count}; "
        f"public_handwriting_count={pub.get('public_sample_count', 0)}; "
        f"torch={torch_version}; torchvision={torchvision_version}; "
        f"onnx={onnx_version}; onnxruntime={onnxruntime_version}"
    )[:1024]

    attribution = str(pub.get("attribution") or "")
    modification = str(pub.get("modification_notice") or "")
    model_provenance = (
        "Phase 5 Task B4 MobileNetV3-Small route-first vision-reservation router with "
        "Handwritten ASAP (CC BY 4.0) training supplementation; "
        "uncertain as vision_required training positive; "
        "project source-group-isolated OOF diagnostics; "
        f"DOI={pub.get('doi', '10.5281/zenodo.8088866')}; "
        f"subset={pub.get('subset_version', 'phase5-asap-subset-v1')}; "
        f"manifest_sha256={pub.get('subset_manifest_sha256', '')[:16]}… "
        f"{attribution} {modification}"
    )[:512]

    licence = (
        "Derived model artefact. Training images include Handwritten ASAP Short "
        "Answer Scoring (CC BY 4.0). Architecture: BSD-3-Clause (torch/torchvision)."
    )[:512]

    record = HandwritingModelRecord(
        schema_version=SCHEMA_VERSION_V3,
        model_family="mobilenet_v3_small_route_first",
        model_version=model_version,
        release_status=release_status,
        training_code_version=training_code_version,
        onnx_opset=ONNX_OPSET,
        onnx_ir_version=None,
        input_tensor_name=ONNX_INPUT_NAME,
        input_dtype="float32",
        input_shape=[None, 3, INPUT_SIZE, INPUT_SIZE],
        dynamic_batch=True,
        colour_mode=spec.colour_mode,  # type: ignore[arg-type]
        channel_order=spec.channel_order,  # type: ignore[arg-type]
        target_width=spec.target_width,
        target_height=spec.target_height,
        resize_policy=spec.resize_policy,  # type: ignore[arg-type]
        aspect_ratio_policy=spec.aspect_ratio_policy,  # type: ignore[arg-type]
        padding_policy=spec.padding_policy,  # type: ignore[arg-type]
        padding_value=float(spec.padding_value),
        interpolation=spec.interpolation,  # type: ignore[arg-type]
        normalisation_mean=list(spec.normalisation_mean),
        normalisation_std=list(spec.normalisation_std),
        output_tensor_name=ONNX_OUTPUT_NAME,
        output_dtype="float32",
        output_semantics=OutputSemantics.ROUTE_FIRST_INDEPENDENT_LOGITS,
        class_order=list(EXPECTED_ROUTE_OUTPUTS),
        public_outcomes=list(PUBLIC_ROUTING_OUTCOMES),
        threshold_set_version=THRESHOLD_SET_VERSION,
        local_ocr_safe_threshold=threshold_metrics.local_ocr_safe_threshold,
        vision_required_threshold=threshold_metrics.vision_required_threshold,
        handwriting_accept_threshold=threshold_metrics.handwriting_accept_threshold,
        training_manifest_sha256=training_manifest_sha256,
        validation_manifest_sha256=validation_manifest_sha256,
        held_out_manifest_sha256=held_out_manifest_sha256,
        model_sha256=model_digest,
        pretrained_weight_provenance=pretrained_provenance[:512],
        model_provenance=model_provenance,
        licence=licence,
        created_at=datetime.now(UTC),
        supported_onnxruntime_version="1.28.0",
        expected_execution_provider="CPUExecutionProvider",
        notes=notes_full,
    )
    (package_dir / "model-record.json").write_text(
        record.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    metrics = HandwritingMetricsRecord(
        schema_version="phase5-handwriting-metrics-v1",
        metrics_kind=MetricsKind.PROJECT_PRIVATE,
        model_version=model_version,
        notes=(
            "source-group-isolated out-of-fold prototype diagnostics; "
            "final fitted model has no independent release held-out evaluation; "
            "route-first vision-reservation decision policy"
        )[:1024],
        handwriting_safe_bypass_recall=threshold_metrics.handwriting_safe_bypass_recall,
        handwriting_to_paddle_leak_count=threshold_metrics.handwritten_to_printed,
        handwriting_to_nontext_count=0,
        class_support=oof_summary.get("class_support"),
    )
    (package_dir / "metrics.json").write_text(
        metrics.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    (package_dir / "README.md").write_text(
        "\n".join(
            [
                "# handwriting_classifier (Phase 5 Task B4 route-first)",
                "",
                f"- model_version: `{model_version}`",
                f"- release_status: `{release_status.value}`",
                f"- threshold_set_version: `{THRESHOLD_SET_VERSION}`",
                "- output_semantics: `route_first_independent_logits`",
                "- outputs: `vision_required`, `handwriting_present` (independent sigmoid)",
                "- public outcomes derived by route-first decision policy",
                "- Model never emits `non_text` (Phase 4 suppresses known non-text).",
                "- Public training supplement: Handwritten ASAP (Zenodo 8088866, CC BY 4.0).",
                "- Safety evaluation remains project-only LOSGO (ASAP is training-only).",
                "- Router remains disabled by default (`HANDWRITING_ROUTER_ENABLED=false`).",
                "- Not wired into live OCR in Task B4.",
                "",
                "## Attribution",
                "",
                attribution or "(see model-record.json provenance)",
                "",
                "## Modification notice",
                "",
                modification or "(see model-record.json provenance)",
                "",
                "Verify:",
                "",
                "```text",
                "pnpm models:handwriting:verify",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    verification = verify_classifier_package(package_dir, allow_test_fixture=False)
    return {
        "package_dir": str(package_dir),
        "model_sha256": model_digest,
        "verification_ok": verification.ready,
        "verification_message": verification.message,
        "verification_failure_code": (
            verification.failure_code.value if verification.failure_code else None
        ),
        "release_status": release_status.value,
    }

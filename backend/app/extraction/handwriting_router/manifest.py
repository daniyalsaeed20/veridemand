"""Strict model-package manifests for the Phase 5 handwriting classifier."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from backend.app.contracts.base import ApiModel
from backend.app.extraction.handwriting_router.constants import (
    EXPECTED_RISK_OUTPUTS,
    HISTORICAL_THREE_CLASS_LABELS,
    PUBLIC_ROUTING_OUTCOMES,
    SCHEMA_VERSION_V1,
    SCHEMA_VERSION_V2,
)
from pydantic import Field, field_validator, model_validator


class ClassifierPackageStatus(StrEnum):
    """Release status of a classifier package."""

    TEST_FIXTURE = "test_fixture"
    EVALUATION_ONLY = "evaluation_only"
    PRODUCTION_CANDIDATE = "production_candidate"
    RELEASED = "released"


class OutputSemantics(StrEnum):
    LOGITS = "logits"
    PROBABILITIES = "probabilities"
    INDEPENDENT_BINARY_RISK_LOGITS = "independent_binary_risk_logits"


class ColourMode(StrEnum):
    RGB = "rgb"
    GRAYSCALE = "grayscale"


class ChannelOrder(StrEnum):
    NCHW = "nchw"
    NHWC = "nhwc"


class ResizePolicy(StrEnum):
    STRETCH = "stretch"
    LETTERBOX = "letterbox"


class AspectRatioPolicy(StrEnum):
    PRESERVE = "preserve"
    IGNORE = "ignore"


class PaddingPolicy(StrEnum):
    CONSTANT = "constant"
    NONE = "none"


class InterpolationMethod(StrEnum):
    BILINEAR = "bilinear"
    NEAREST = "nearest"
    BICUBIC = "bicubic"


class MetricsKind(StrEnum):
    SYNTHETIC_TEST = "synthetic_test"
    TRAINING = "training"
    VALIDATION = "validation"
    HELD_OUT = "held_out"
    PROJECT_PRIVATE = "project_private"
    PUBLIC = "public"


class HandwritingModelRecord(ApiModel):
    """Strict model-record.json schema (extra fields forbidden).

    Supports:
    - v1 historical three-class packages (test fixtures / baselines)
    - v2 dual-risk production-candidate packages (Task B3)
    """

    schema_version: Literal["phase5-handwriting-classifier-v1", "phase5-handwriting-classifier-v2"]
    model_family: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=128)
    release_status: ClassifierPackageStatus
    training_code_version: str = Field(min_length=1, max_length=128)
    onnx_opset: int = Field(ge=1, le=25)
    onnx_ir_version: int | None = Field(default=None, ge=1)
    input_tensor_name: str = Field(min_length=1, max_length=128)
    input_dtype: Literal["float32"]
    input_shape: list[int | None] = Field(min_length=4, max_length=4)
    dynamic_batch: bool
    colour_mode: ColourMode
    channel_order: ChannelOrder
    target_width: int = Field(ge=8, le=1024)
    target_height: int = Field(ge=8, le=1024)
    resize_policy: ResizePolicy
    aspect_ratio_policy: AspectRatioPolicy
    padding_policy: PaddingPolicy
    padding_value: float = Field(ge=0.0, le=255.0)
    interpolation: InterpolationMethod
    normalisation_mean: list[float] = Field(min_length=1, max_length=3)
    normalisation_std: list[float] = Field(min_length=1, max_length=3)
    output_tensor_name: str = Field(min_length=1, max_length=128)
    output_dtype: Literal["float32"]
    output_semantics: OutputSemantics
    # v1: three public classes; v2: two risk heads (not public outcomes).
    class_order: list[str] = Field(min_length=2, max_length=3)
    public_outcomes: list[str] | None = Field(default=None)
    threshold_set_version: str = Field(min_length=1, max_length=128)
    handwriting_accept_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    handwriting_safe_low_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    non_text_accept_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    non_text_safe_low_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    training_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    validation_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    held_out_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pretrained_weight_provenance: str = Field(min_length=1, max_length=512)
    model_provenance: str = Field(min_length=1, max_length=512)
    licence: str = Field(min_length=1, max_length=512)
    created_at: datetime
    supported_onnxruntime_version: str = Field(min_length=1, max_length=64)
    expected_execution_provider: Literal["CPUExecutionProvider"]
    notes: str | None = Field(default=None, max_length=1024)

    @field_validator("normalisation_std")
    @classmethod
    def _nonzero_std(cls, value: list[float]) -> list[float]:
        if any(abs(v) < 1e-12 for v in value):
            raise ValueError("normalisation_std entries must be non-zero.")
        return value

    @model_validator(mode="after")
    def _schema_consistency(self) -> HandwritingModelRecord:
        channels = 1 if self.colour_mode is ColourMode.GRAYSCALE else 3
        if len(self.normalisation_mean) != channels or len(self.normalisation_std) != channels:
            raise ValueError("normalisation mean/std length must match colour_mode channels.")
        if self.channel_order is ChannelOrder.NCHW:
            c_dim = self.input_shape[1]
            h_dim = self.input_shape[2]
            w_dim = self.input_shape[3]
        else:
            h_dim = self.input_shape[1]
            w_dim = self.input_shape[2]
            c_dim = self.input_shape[3]
        if c_dim not in (None, channels):
            raise ValueError("input_shape channel dimension must match colour_mode.")
        if h_dim not in (None, self.target_height):
            raise ValueError("input_shape height must match target_height or be dynamic.")
        if w_dim not in (None, self.target_width):
            raise ValueError("input_shape width must match target_width or be dynamic.")
        if self.dynamic_batch and self.input_shape[0] is not None:
            raise ValueError("dynamic_batch requires null batch dimension.")
        if not self.dynamic_batch and self.input_shape[0] != 1:
            raise ValueError("fixed batch packages must declare batch size 1.")

        if self.schema_version == SCHEMA_VERSION_V1:
            if self.class_order != list(HISTORICAL_THREE_CLASS_LABELS):
                raise ValueError(
                    f"v1 class_order must be exactly {list(HISTORICAL_THREE_CLASS_LABELS)}."
                )
            if self.output_semantics not in {
                OutputSemantics.LOGITS,
                OutputSemantics.PROBABILITIES,
            }:
                raise ValueError("v1 packages require logits or probabilities semantics.")
            if self.output_tensor_name not in {"logits", "probabilities"}:
                raise ValueError("v1 output_tensor_name must be logits or probabilities.")
        else:
            # v2 dual-risk
            if self.class_order != list(EXPECTED_RISK_OUTPUTS):
                raise ValueError(
                    f"v2 class_order (risk outputs) must be exactly {list(EXPECTED_RISK_OUTPUTS)}."
                )
            if self.output_semantics is not OutputSemantics.INDEPENDENT_BINARY_RISK_LOGITS:
                raise ValueError(
                    "v2 packages require output_semantics=independent_binary_risk_logits."
                )
            if self.output_tensor_name != "risk_logits":
                raise ValueError("v2 output_tensor_name must be risk_logits.")
            if self.public_outcomes != list(PUBLIC_ROUTING_OUTCOMES):
                raise ValueError(
                    f"v2 public_outcomes must be exactly {list(PUBLIC_ROUTING_OUTCOMES)}."
                )
            thr = (
                self.handwriting_accept_threshold,
                self.handwriting_safe_low_threshold,
                self.non_text_accept_threshold,
                self.non_text_safe_low_threshold,
            )
            if any(v is None for v in thr):
                if self.release_status in {
                    ClassifierPackageStatus.PRODUCTION_CANDIDATE,
                    ClassifierPackageStatus.RELEASED,
                }:
                    raise ValueError(
                        "v2 production packages require all four dual-risk thresholds."
                    )
            else:
                assert self.handwriting_safe_low_threshold is not None
                assert self.handwriting_accept_threshold is not None
                assert self.non_text_safe_low_threshold is not None
                assert self.non_text_accept_threshold is not None
                if not (
                    self.handwriting_safe_low_threshold < self.handwriting_accept_threshold
                    and self.non_text_safe_low_threshold < self.non_text_accept_threshold
                ):
                    raise ValueError("dual-risk thresholds must satisfy safe_low < accept.")

        production_like = self.release_status in {
            ClassifierPackageStatus.PRODUCTION_CANDIDATE,
            ClassifierPackageStatus.RELEASED,
        }
        if production_like and not all(
            [
                self.training_manifest_sha256,
                self.validation_manifest_sha256,
                self.held_out_manifest_sha256,
            ]
        ):
            raise ValueError(
                "production_candidate/released packages require train/val/held-out "
                "manifest SHA-256 hashes."
            )
        return self

    @property
    def is_dual_risk(self) -> bool:
        return self.schema_version == SCHEMA_VERSION_V2

    @property
    def expected_output_dim(self) -> int:
        return 2 if self.is_dual_risk else 3


class HandwritingMetricsRecord(ApiModel):
    """Strict metrics.json schema. Does not invent evaluation claims."""

    schema_version: Literal["phase5-handwriting-metrics-v1"]
    metrics_kind: MetricsKind
    model_version: str = Field(min_length=1, max_length=128)
    notes: str | None = Field(default=None, max_length=1024)
    handwriting_safe_bypass_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    handwriting_to_paddle_leak_count: int | None = Field(default=None, ge=0)
    handwriting_to_nontext_count: int | None = Field(default=None, ge=0)
    class_support: dict[str, int] | None = None

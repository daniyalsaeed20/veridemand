"""Strict model-package manifests for the Phase 5 handwriting classifier."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from backend.app.contracts.base import ApiModel
from backend.app.extraction.handwriting_router.constants import EXPECTED_MODEL_LABELS
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
    """Strict model-record.json schema (extra fields forbidden)."""

    schema_version: Literal["phase5-handwriting-classifier-v1"]
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
    class_order: list[str] = Field(min_length=3, max_length=3)
    threshold_set_version: str = Field(min_length=1, max_length=128)
    training_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    validation_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    held_out_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pretrained_weight_provenance: str = Field(min_length=1, max_length=512)
    model_provenance: str = Field(min_length=1, max_length=512)
    licence: str = Field(min_length=1, max_length=128)
    created_at: datetime
    supported_onnxruntime_version: str = Field(min_length=1, max_length=64)
    expected_execution_provider: Literal["CPUExecutionProvider"]
    notes: str | None = Field(default=None, max_length=1024)

    @field_validator("class_order")
    @classmethod
    def _exact_labels(cls, value: list[str]) -> list[str]:
        expected = list(EXPECTED_MODEL_LABELS)
        if value != expected:
            raise ValueError(f"class_order must be exactly {expected}.")
        return value

    @field_validator("normalisation_std")
    @classmethod
    def _nonzero_std(cls, value: list[float]) -> list[float]:
        if any(abs(v) < 1e-12 for v in value):
            raise ValueError("normalisation_std entries must be non-zero.")
        return value

    @model_validator(mode="after")
    def _channel_consistency(self) -> HandwritingModelRecord:
        channels = 1 if self.colour_mode is ColourMode.GRAYSCALE else 3
        if len(self.normalisation_mean) != channels or len(self.normalisation_std) != channels:
            raise ValueError("normalisation mean/std length must match colour_mode channels.")
        if self.channel_order is ChannelOrder.NCHW:
            # [N, C, H, W]
            c_dim = self.input_shape[1]
            h_dim = self.input_shape[2]
            w_dim = self.input_shape[3]
        else:
            # [N, H, W, C]
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


class HandwritingMetricsRecord(ApiModel):
    """Strict metrics.json schema. Does not invent evaluation claims."""

    schema_version: Literal["phase5-handwriting-metrics-v1"]
    metrics_kind: MetricsKind
    model_version: str = Field(min_length=1, max_length=128)
    notes: str | None = Field(default=None, max_length=1024)
    # Optional sparse numeric fields — no fabricated release gates.
    handwriting_safe_bypass_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    handwriting_to_paddle_leak_count: int | None = Field(default=None, ge=0)
    class_support: dict[str, int] | None = None

"""Deterministic training configuration for Phase 5 Task B2."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from typing import Any, Literal

CLASS_ORDER: tuple[str, str, str] = ("printed", "handwritten", "non_text")
IMAGENET_MEAN: tuple[float, float, float] = (0.485, 0.456, 0.406)
IMAGENET_STD: tuple[float, float, float] = (0.229, 0.224, 0.225)
INPUT_SIZE = 224
PADDING_VALUE = 255.0  # scanned-paper white
ONNX_OPSET = 17
ONNX_INPUT_NAME = "image"
ONNX_OUTPUT_NAME = "logits"
PARITY_TOLERANCE = 1e-4
SYNTHETIC_NONTEXT_COUNT = 400
SYNTHETIC_SOURCE_GROUP_PREFIX = "srcgrp_synth_nt_"

BalancingMethod = Literal["class_weighted", "balanced_sampler", "project_hw_weighted"]
AugStrength = Literal["default", "stronger"]
PublicAsapVariant = Literal["none", "light", "medium"]


@dataclass(frozen=True)
class TrainConfig:
    """Explicit, hashable training configuration."""

    name: str
    random_seed: int = 42
    torch_seed: int = 42
    numpy_seed: int = 42
    dataloader_seed: int = 42
    architecture: str = "mobilenet_v3_small"
    weights_enum: str = "MobileNet_V3_Small_Weights.DEFAULT"
    input_size: int = INPUT_SIZE
    batch_size: int = 16
    stage1_epochs: int = 3
    stage2_epochs: int = 5
    stage1_lr: float = 1e-3
    stage2_lr: float = 1e-4
    weight_decay: float = 1e-4
    balancing: BalancingMethod = "class_weighted"
    aug_strength: AugStrength = "default"
    augmentation_version: str = "phase5-conservative-aug-v1"
    preprocessing_version: str = "phase5-letterbox-224-imagenet-v1"
    checkpoint_rule: str = "fixed_epoch_budget_stage2_final"
    synthetic_nontext_count: int = 300
    num_workers: int = 0
    public_asap_variant: PublicAsapVariant = "medium"
    # Multiplier applied to project (non-ASAP) handwritten sample weights.
    project_handwriting_sample_multiplier: float = 1.0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def config_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode("utf-8")).hexdigest()


# At most three materially different Task B2 configurations.
CANDIDATE_CONFIGS: tuple[TrainConfig, ...] = (
    TrainConfig(
        name="asap_light",
        balancing="class_weighted",
        aug_strength="default",
        public_asap_variant="light",
        project_handwriting_sample_multiplier=1.0,
        notes="~150 ASAP public HW + project labels; class-weighted CE.",
    ),
    TrainConfig(
        name="asap_medium",
        balancing="class_weighted",
        aug_strength="default",
        public_asap_variant="medium",
        project_handwriting_sample_multiplier=1.0,
        notes="All QC-passed ASAP public HW + project labels; class-weighted CE.",
    ),
    TrainConfig(
        name="asap_medium_project_weighted",
        balancing="project_hw_weighted",
        aug_strength="default",
        public_asap_variant="medium",
        project_handwriting_sample_multiplier=4.0,
        notes=(
            "All ASAP public HW with project-handwriting sampling multiplier=4 "
            "(oversamples do not count as new human labels)."
        ),
    ),
)


@dataclass
class ThresholdCandidate:
    printed: float
    handwritten: float
    non_text: float
    minimum_class_margin: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.printed, self.handwritten, self.non_text, self.minimum_class_margin)


def default_threshold_grid() -> list[ThresholdCandidate]:
    """Bounded deterministic threshold search grid."""

    printed = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]
    handwritten = [0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
    non_text = [0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
    margins = [0.05, 0.08, 0.10, 0.12, 0.15, 0.20]
    out: list[ThresholdCandidate] = []
    for p in printed:
        for h in handwritten:
            for n in non_text:
                for m in margins:
                    out.append(
                        ThresholdCandidate(
                            printed=p, handwritten=h, non_text=n, minimum_class_margin=m
                        )
                    )
    return out


@dataclass
class RuntimePreprocessSpec:
    """Contract written into model-record.json (must match ORT preprocess)."""

    colour_mode: str = "rgb"
    channel_order: str = "nchw"
    target_width: int = INPUT_SIZE
    target_height: int = INPUT_SIZE
    resize_policy: str = "letterbox"
    aspect_ratio_policy: str = "preserve"
    padding_policy: str = "constant"
    padding_value: float = PADDING_VALUE
    interpolation: str = "bilinear"
    normalisation_mean: list[float] = field(default_factory=lambda: list(IMAGENET_MEAN))
    normalisation_std: list[float] = field(default_factory=lambda: list(IMAGENET_STD))

"""Deterministic training configuration for Phase 5 Task B3 dual-risk."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from typing import Any, Literal

from model_development.handwriting_classifier import RISK_ORDER, TRAINING_LABELS

# Back-compat export for evaluate helpers.
CLASS_ORDER = TRAINING_LABELS

IMAGENET_MEAN: tuple[float, float, float] = (0.485, 0.456, 0.406)
IMAGENET_STD: tuple[float, float, float] = (0.229, 0.224, 0.225)
INPUT_SIZE = 224
PADDING_VALUE = 255.0  # scanned-paper white
ONNX_OPSET = 17
ONNX_INPUT_NAME = "image"
ONNX_OUTPUT_NAME = "risk_logits"
PARITY_TOLERANCE = 1e-4
SYNTHETIC_NONTEXT_COUNT = 400
SYNTHETIC_SOURCE_GROUP_PREFIX = "srcgrp_synth_nt_"

LossName = Literal["weighted_bce", "asymmetric_bce", "focal"]
AugStrength = Literal["default", "stronger"]
PublicAsapVariant = Literal["none", "light", "medium"]


@dataclass(frozen=True)
class TrainConfig:
    """Explicit, hashable dual-risk training configuration."""

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
    loss: LossName = "weighted_bce"
    handwriting_fn_multiplier: float = 3.0
    focal_alpha: float = 0.25
    focal_gamma: float = 2.0
    # A-priori hard-example emphasis on signature/cursive project seeds (not OOF-mined).
    hard_example_emphasis: bool = False
    hard_example_multiplier: float = 2.0
    aug_strength: AugStrength = "default"
    augmentation_version: str = "phase5-conservative-aug-v1"
    preprocessing_version: str = "phase5-letterbox-224-imagenet-v1"
    checkpoint_rule: str = "fixed_epoch_budget_stage2_final"
    synthetic_nontext_count: int = 300
    num_workers: int = 0
    public_asap_variant: PublicAsapVariant = "medium"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def config_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode("utf-8")).hexdigest()


# At most three materially different Task B3 configurations (loss variants).
CANDIDATE_CONFIGS: tuple[TrainConfig, ...] = (
    TrainConfig(
        name="dual_risk_weighted_bce",
        loss="weighted_bce",
        public_asap_variant="medium",
        hard_example_emphasis=False,
        notes="Config A: fold-derived pos_weight BCE on both risk heads; ASAP medium.",
    ),
    TrainConfig(
        name="dual_risk_asymmetric_bce",
        loss="asymmetric_bce",
        handwriting_fn_multiplier=3.0,
        public_asap_variant="medium",
        hard_example_emphasis=True,
        hard_example_multiplier=2.0,
        notes=(
            "Config B: asymmetric HW FN multiplier=3.0 + a-priori signature/cursive "
            "emphasis (not OOF-mined); ASAP medium."
        ),
    ),
    TrainConfig(
        name="dual_risk_focal",
        loss="focal",
        focal_alpha=0.25,
        focal_gamma=2.0,
        public_asap_variant="medium",
        hard_example_emphasis=False,
        notes="Config C: binary focal loss alpha=0.25 gamma=2.0; ASAP medium.",
    ),
)


@dataclass(frozen=True)
class ThresholdCandidate:
    """Four dual-risk thresholds with ordering constraints enforced by the grid."""

    handwriting_accept_threshold: float
    handwriting_safe_low_threshold: float
    non_text_accept_threshold: float
    non_text_safe_low_threshold: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (
            self.handwriting_accept_threshold,
            self.handwriting_safe_low_threshold,
            self.non_text_accept_threshold,
            self.non_text_safe_low_threshold,
        )

    def is_ordered(self) -> bool:
        return (
            self.handwriting_safe_low_threshold < self.handwriting_accept_threshold
            and self.non_text_safe_low_threshold < self.non_text_accept_threshold
        )


def default_threshold_grid() -> list[ThresholdCandidate]:
    """Bounded deterministic dual-risk threshold search grid."""

    hw_accept = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]
    hw_safe = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
    nt_accept = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]
    nt_safe = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
    out: list[ThresholdCandidate] = []
    for ha in hw_accept:
        for hs in hw_safe:
            if not (hs < ha):
                continue
            for na in nt_accept:
                for ns in nt_safe:
                    if not (ns < na):
                        continue
                    out.append(
                        ThresholdCandidate(
                            handwriting_accept_threshold=ha,
                            handwriting_safe_low_threshold=hs,
                            non_text_accept_threshold=na,
                            non_text_safe_low_threshold=ns,
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
    normalisation_mean: tuple[float, float, float] = field(default_factory=lambda: IMAGENET_MEAN)
    normalisation_std: tuple[float, float, float] = field(default_factory=lambda: IMAGENET_STD)


def risk_target_for_label(label: str) -> tuple[float, float]:
    """Map human class to dual-risk training targets."""

    if label == "printed":
        return (0.0, 0.0)
    if label == "handwritten":
        return (1.0, 0.0)
    if label == "non_text":
        return (0.0, 1.0)
    raise ValueError(f"Label {label!r} is not a dual-risk training target")


def assert_risk_order() -> None:
    assert RISK_ORDER == ("handwriting_risk", "non_text_risk")

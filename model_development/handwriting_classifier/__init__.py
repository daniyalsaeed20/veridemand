"""Phase 5 Task B3 safety-first dual-risk handwriting classifier training.

Not imported by FastAPI or production OCR. Torch stays in model-dev only.

Task B / B2 three-class softmax baselines remain documented as
prototype baseline — superseded for safety evaluation.
"""

from __future__ import annotations

RISK_ORDER: tuple[str, str] = ("handwriting_risk", "non_text_risk")
PUBLIC_OUTCOMES: tuple[str, str, str, str] = (
    "printed",
    "handwritten",
    "uncertain",
    "non_text",
)
# Human training labels (uncertain is challenge-only, never a training target).
TRAINING_LABELS: tuple[str, str, str] = ("printed", "handwritten", "non_text")
# Back-compat alias used by older evaluation helpers that still enumerate human classes.
CLASS_ORDER: tuple[str, str, str] = TRAINING_LABELS

TRAINING_MANIFEST_VERSION = "phase5-classifier-training-manifest-v1"
SCHEMA_VERSION = "phase5-classifier-training-schema-v1"
THRESHOLD_SET_VERSION = "phase5-task-b3-dual-risk-v1"
MODEL_FAMILY = "mobilenet_v3_small_dual_risk"
MODEL_VERSION = "phase5-task-b3-dual-risk-v1"
AUGMENTATION_VERSION = "phase5-conservative-aug-v1"
PREPROCESSING_VERSION = "phase5-letterbox-224-imagenet-v1"
ARCHITECTURE_VERSION = "mobilenet_v3_small_dual_risk_v1"

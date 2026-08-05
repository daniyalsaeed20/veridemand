"""Phase 5 Task B4 route-first vision-reservation handwriting classifier.

Not imported by FastAPI or production OCR. Torch stays in model-dev only.

Task B / B2 three-class softmax and Task B3 dual-risk baselines remain
documented as failed prototypes — superseded for safety evaluation.
"""

from __future__ import annotations

# Primary ONNX / training head order (independent sigmoid, never softmax).
ROUTE_ORDER: tuple[str, str] = ("vision_required", "handwriting_present")
# Back-compat alias used by older imports during the B3→B4 transition.
RISK_ORDER: tuple[str, str] = ROUTE_ORDER

PUBLIC_OUTCOMES: tuple[str, str, str, str] = (
    "printed",
    "handwritten",
    "uncertain",
    "non_text",
)
# Human training labels (uncertain is a vision_required positive with HW loss masked).
TRAINING_LABELS: tuple[str, str, str, str] = (
    "printed",
    "handwritten",
    "uncertain",
    "non_text",
)
CLASS_ORDER: tuple[str, str, str, str] = TRAINING_LABELS

TRAINING_MANIFEST_VERSION = "phase5-classifier-training-manifest-v1"
SCHEMA_VERSION = "phase5-classifier-training-schema-v1"
THRESHOLD_SET_VERSION = "phase5-task-b4-route-first-v1"
MODEL_FAMILY = "mobilenet_v3_small_route_first"
MODEL_VERSION = "phase5-task-b4-route-first-v1"
AUGMENTATION_VERSION = "phase5-conservative-aug-v1"
PREPROCESSING_VERSION = "phase5-letterbox-224-imagenet-v1"
ARCHITECTURE_VERSION = "mobilenet_v3_small_route_first_v1"

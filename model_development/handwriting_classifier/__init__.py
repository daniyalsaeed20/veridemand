"""Phase 5 Task B handwriting classifier training package.

Not imported by FastAPI or production OCR. Torch stays in model-dev only.
"""

from __future__ import annotations

CLASS_ORDER: tuple[str, str, str] = ("printed", "handwritten", "non_text")
TRAINING_MANIFEST_VERSION = "phase5-classifier-training-manifest-v1"
SCHEMA_VERSION = "phase5-classifier-training-schema-v1"
THRESHOLD_SET_VERSION = "phase5-task-b-prototype-v1"
MODEL_FAMILY = "mobilenet_v3_small_writing_style"
MODEL_VERSION = "phase5-task-b-v1"
AUGMENTATION_VERSION = "phase5-conservative-aug-v1"
PREPROCESSING_VERSION = "phase5-letterbox-224-imagenet-v1"
ARCHITECTURE_VERSION = "mobilenet_v3_small_head3_v1"

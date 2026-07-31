"""Phase 5 crop-dataset constants and versioned policies."""

from __future__ import annotations

from typing import Final, Literal

SCHEMA_VERSION: Final = "phase5-dataset-schema-v1"
LABEL_SCHEMA_VERSION: Final = "phase5-human-label-v1"
CROP_PADDING_VERSION: Final = "phase5-crop-pad-v1"
REVIEW_POLICY_VERSION: Final = "phase5-review-policy-v1"
SPLIT_ALGORITHM_VERSION: Final = "phase5-group-split-v1"
DUPLICATE_POLICY_VERSION: Final = "phase5-duplicate-policy-v1"
QUEUE_ALGORITHM_VERSION: Final = "phase5-primary-queue-v1"
REVIEW_QUEUE_VERSION: Final = "phase5-primary-review-queue-v1"
PROVENANCE_AUDIT_VERSION: Final = "phase5-provenance-audit-v1"
SOURCE_MANIFEST_DEDUPE_VERSION: Final = "phase5-source-manifest-dedupe-v1"
BLOCK_COVERAGE_VERSION: Final = "phase5-block-coverage-v1"
BLOCK_COVERAGE_GAP_THRESHOLD: Final = 0.90
COVERAGE_QUEUE_VERSION: Final = "phase5-coverage-queue-v1"
COVERAGE_EVENT_VERSION: Final = "phase5-coverage-event-v1"
PILOT_VERSION: Final = "phase5-annotation-pilot-v1"
PILOT_SAMPLING_VERSION: Final = "phase5-annotation-pilot-sampling-v1"
PILOT_PRIMARY_QUEUE_VERSION: Final = "phase5-pilot-primary-v1"
PILOT_SECONDARY_QUEUE_VERSION: Final = "phase5-pilot-secondary-v1"
PILOT_PRIMARY_SEED: Final = 3101
PILOT_SECONDARY_SEED: Final = 3102
PILOT_TARGET_SIZE: Final = 600
PILOT_SOFT_CAP_PER_PAGE: Final = 5
PILOT_HARD_CAP_PER_PAGE: Final = 10
FULL_QUEUE_AUTHORISATION_NOTE: Final = (
    "full primary queue — not authorised for review until pilot approval"
)

# Fixed padding: 8% of the longer side of the source region bbox (normalised).
CROP_PADDING_RATIO: Final = 0.08

SourceFamily = Literal[
    "medical_form",
    "police_form",
    "billing_ledger",
    "fax_record",
    "insurance_letter",
    "image_document",
    "other",
]
SOURCE_FAMILIES: Final[frozenset[str]] = frozenset(
    {
        "medical_form",
        "police_form",
        "billing_ledger",
        "fax_record",
        "insurance_letter",
        "image_document",
        "other",
    }
)

# Average-hash size for perceptual duplicate warnings (stdlib Pillow + NumPy).
PERCEPTUAL_HASH_SIZE: Final = 8
PERCEPTUAL_HAMMING_WARN_THRESHOLD: Final = 5

HumanLabel = Literal["printed", "handwritten", "uncertain", "non_text"]
HUMAN_LABELS: Final[frozenset[str]] = frozenset({"printed", "handwritten", "uncertain", "non_text"})
# Initial 3-class training excludes uncertain (challenge / vision-reserved).
MODEL_TRAINING_LABELS: Final[frozenset[str]] = frozenset({"printed", "handwritten", "non_text"})

CandidateSource = Literal[
    "visual_detection",
    "full_page_ocr",
    "targeted_repair",
    "heuristic_region",
    "noise_region",
    "manual_region",
    "synthetic_negative",
]
CANDIDATE_SOURCES: Final[frozenset[str]] = frozenset(
    {
        "visual_detection",
        "full_page_ocr",
        "targeted_repair",
        "heuristic_region",
        "noise_region",
        "manual_region",
        "synthetic_negative",
    }
)

ReviewerRole = Literal["primary", "secondary", "adjudicator"]
ReviewAction = Literal[
    "label",
    "skip",
    "exclude",
    "flag_quality",
    "undo_mark",
]
ResolutionStatus = Literal[
    "unreviewed",
    "single_review",
    "agreed",
    "conflict",
    "adjudicated",
    "excluded",
    "invalidated_hash_mismatch",
]
SplitName = Literal["train", "val", "test", "held_out"]

CoverageOutcome = Literal[
    "coverage_appears_complete",
    "missing_region",
    "crop_too_tight",
    "crop_too_broad",
    "duplicate_only",
    "page_requires_manual_review",
    "page_not_reviewable",
]
COVERAGE_OUTCOMES: Final[frozenset[str]] = frozenset(
    {
        "coverage_appears_complete",
        "missing_region",
        "crop_too_tight",
        "crop_too_broad",
        "duplicate_only",
        "page_requires_manual_review",
        "page_not_reviewable",
    }
)

CropQualityFlag = Literal[
    "crop_too_tight",
    "crop_too_broad",
    "blurred",
    "low_resolution",
    "mixed_content",
    "partial_characters",
    "rotation_problem",
    "possible_duplicate",
    "requires_page_context",
]
CROP_QUALITY_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "crop_too_tight",
        "crop_too_broad",
        "blurred",
        "low_resolution",
        "mixed_content",
        "partial_characters",
        "rotation_problem",
        "possible_duplicate",
        "requires_page_context",
    }
)

QueueName = Literal["pilot-primary", "pilot-secondary", "full-primary", "adjudication"]
QUEUE_NAMES: Final[frozenset[str]] = frozenset(
    {"pilot-primary", "pilot-secondary", "full-primary", "adjudication"}
)

PRIVATE_PHASE5_REL: Final = "fixtures/private/phase5"
PRIVATE_SUBDIRS: Final[tuple[str, ...]] = (
    "sources",
    "pages",
    "crops",
    "manifests",
    "reports",
    "locks",
    "backups",
    "coverage",
)
MANIFEST_FILES: Final[tuple[str, ...]] = (
    "document-manifest.jsonl",
    "source-manifest.jsonl",
    "crop-manifest.jsonl",
    "review-events.jsonl",
    "resolved-labels.jsonl",
    "exclusions.jsonl",
    "split-manifest.jsonl",
    "duplicate-families.jsonl",
    "primary-review-queue.jsonl",
    "pilot-manifest.jsonl",
    "pilot-primary-queue.jsonl",
    "pilot-secondary-queue.jsonl",
    "adjudication-queue.jsonl",
    "coverage-queue.jsonl",
    "coverage-events.jsonl",
    "block-coverage-audit.jsonl",
    "provenance-audit.json",
    "context-review-worklist.jsonl",
)

"""OCR runtime readiness and retry contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from backend.app.contracts.base import ApiModel


class OcrRuntimeState(StrEnum):
    """Process-wide OCR runtime lifecycle state."""

    NOT_STARTED = "not_started"
    STARTING = "starting"
    LOADING_DETECTOR = "loading_detector"
    LOADING_RECOGNIZER = "loading_recognizer"
    WARMING_UP = "warming_up"
    READY = "ready"
    FAILED = "failed"
    DISABLED = "disabled"


class OcrRuntimeStage(StrEnum):
    """Operator-facing startup stages (progress steps 1-5)."""

    CHECKING_CONFIGURATION = "checking_configuration"
    VERIFYING_MODELS = "verifying_models"
    LOADING_DETECTOR = "loading_detector"
    LOADING_RECOGNIZER = "loading_recognizer"
    WARMING_UP = "warming_up"


class OcrComponentStatus(StrEnum):
    """Coarse status for detector / recognizer / model verification."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    READY = "ready"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class OcrRuntimeErrorCode(StrEnum):
    """Stable OCR readiness / recovery error codes (snake_case)."""

    OCR_DISABLED = "ocr_disabled"
    OCR_CONFIGURATION_INVALID = "ocr_configuration_invalid"
    OCR_MODELS_MISSING = "ocr_models_missing"
    OCR_MODEL_INTEGRITY_FAILED = "ocr_model_integrity_failed"
    OCR_DEPENDENCY_IMPORT_FAILED = "ocr_dependency_import_failed"
    OCR_DLL_LOAD_FAILED = "ocr_dll_load_failed"
    OCR_DETECTOR_LOAD_FAILED = "ocr_detector_load_failed"
    OCR_RECOGNIZER_LOAD_FAILED = "ocr_recognizer_load_failed"
    OCR_WARMUP_FAILED = "ocr_warmup_failed"
    OCR_STARTUP_TIMEOUT = "ocr_startup_timeout"
    OCR_OUT_OF_MEMORY = "ocr_out_of_memory"
    OCR_INITIALIZATION_ALREADY_RUNNING = "ocr_initialization_already_running"
    OCR_UNKNOWN_FAILURE = "ocr_unknown_failure"
    BACKEND_UNREACHABLE = "backend_unreachable"


class OcrPythonEnvironmentKind(StrEnum):
    """Sanitized kind of the Python environment running the OCR backend."""

    OCR = "ocr"
    MODEL_DEV = "model_dev"
    MIXED = "mixed"
    DEFAULT = "default"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class OcrRecoveryAction(StrEnum):
    """Operator recovery action for the current OCR failure."""

    NONE = "none"
    RETRY_OCR_RUNTIME = "retry_ocr_runtime"
    RESTART_BACKEND_IN_OCR_ENVIRONMENT = "restart_backend_in_ocr_environment"


OCR_PROGRESS_STAGES: tuple[OcrRuntimeStage, ...] = (
    OcrRuntimeStage.CHECKING_CONFIGURATION,
    OcrRuntimeStage.VERIFYING_MODELS,
    OcrRuntimeStage.LOADING_DETECTOR,
    OcrRuntimeStage.LOADING_RECOGNIZER,
    OcrRuntimeStage.WARMING_UP,
)

OCR_STAGE_LABELS: dict[OcrRuntimeStage, str] = {
    OcrRuntimeStage.CHECKING_CONFIGURATION: "Checking OCR configuration",
    OcrRuntimeStage.VERIFYING_MODELS: "Verifying model files",
    OcrRuntimeStage.LOADING_DETECTOR: "Loading detector",
    OcrRuntimeStage.LOADING_RECOGNIZER: "Loading recognizer",
    OcrRuntimeStage.WARMING_UP: "Warming OCR runtime",
}


class OcrRuntimeStatus(ApiModel):
    """Structured OCR runtime readiness status for operators and the UI."""

    state: OcrRuntimeState = Field(description="Current OCR runtime lifecycle state.")
    stage: OcrRuntimeStage | None = Field(
        default=None, description="Active or last startup stage when applicable."
    )
    stage_index: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="1-based progress step when a startup stage is active.",
    )
    stage_count: int = Field(default=5, ge=1, description="Total startup progress steps.")
    stage_label: str | None = Field(
        default=None, description="Human-readable label for the current stage."
    )
    attempt_id: str | None = Field(
        default=None, description="Opaque identifier for the current initialization attempt."
    )
    attempt_number: int = Field(
        default=0, ge=0, description="Monotonic initialization attempt counter."
    )
    attempt_started_at: datetime | None = Field(
        default=None, description="UTC time when the current attempt started."
    )
    last_transition_at: datetime | None = Field(
        default=None, description="UTC time of the last state/stage transition."
    )
    ready: bool = Field(description="True when printed OCR can accept work.")
    retryable: bool = Field(
        description="True when an operator Retry OCR action may succeed after correction."
    )
    restart_required: bool = Field(
        default=False,
        description="True when the API process must be restarted in the OCR-only environment.",
    )
    recovery_action: OcrRecoveryAction = Field(
        default=OcrRecoveryAction.NONE,
        description="Structured recovery action for operators and the UI.",
    )
    error_code: OcrRuntimeErrorCode | None = Field(
        default=None, description="Stable failure code when state is failed or disabled."
    )
    user_message: str | None = Field(
        default=None, description="Operator-readable explanation of the current state."
    )
    operator_hint: str | None = Field(
        default=None, description="Likely corrective action for the operator."
    )
    technical_detail: str | None = Field(
        default=None,
        description="Sanitized technical summary (no secrets, paths, OCR text, or stack traces).",
    )
    retry_after_seconds: int | None = Field(
        default=None,
        ge=0,
        description="Suggested client delay before the next readiness poll.",
    )
    detector_status: OcrComponentStatus = Field(
        default=OcrComponentStatus.PENDING, description="Detector load status."
    )
    recognizer_status: OcrComponentStatus = Field(
        default=OcrComponentStatus.PENDING, description="Recognizer load status."
    )
    model_verification_status: OcrComponentStatus = Field(
        default=OcrComponentStatus.PENDING, description="Local model verification status."
    )
    python_environment_kind: OcrPythonEnvironmentKind = Field(
        default=OcrPythonEnvironmentKind.UNKNOWN,
        description="Sanitized Python environment kind for the OCR backend process.",
    )
    python_executable_environment: str | None = Field(
        default=None,
        description="Sanitized environment directory name only (never a full user path).",
    )
    torch_present: bool | None = Field(
        default=None,
        description="True when the torch package is discoverable without importing it.",
    )
    torchvision_present: bool | None = Field(
        default=None,
        description="True when the torchvision package is discoverable without importing it.",
    )
    paddle_present: bool | None = Field(
        default=None,
        description="True when the paddle package is discoverable without importing it.",
    )


class OcrRetryAcceptedResponse(ApiModel):
    """202 Accepted response for POST /api/v1/runtime/ocr/retry."""

    attempt_id: str = Field(description="Initialization attempt identifier.")
    state: OcrRuntimeState = Field(description="Current OCR runtime state after accepting retry.")
    stage: OcrRuntimeStage | None = Field(
        default=None, description="Current startup stage when known."
    )
    status_url: Literal["/health/ready"] = Field(
        default="/health/ready",
        description="Observational readiness URL for status polling.",
    )

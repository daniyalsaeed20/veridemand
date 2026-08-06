"""Runtime control endpoints (OCR readiness retry)."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from backend.app.contracts.errors import ApiErrorEnvelope, ErrorCode
from backend.app.contracts.ocr_runtime import OcrRetryAcceptedResponse, OcrRuntimeState
from backend.app.extraction.visual.ocr_readiness import is_retryable
from backend.app.extraction.visual.worker_manager import OcrWorkerManager
from backend.app.observability.errors import ApiException
from backend.app.settings.config import Settings

router = APIRouter(tags=["runtime"])


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _ocr_manager(request: Request) -> OcrWorkerManager | None:
    manager = getattr(request.app.state, "ocr_worker_manager", None)
    return manager if isinstance(manager, OcrWorkerManager) else None


@router.post(
    "/runtime/ocr/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=OcrRetryAcceptedResponse,
    summary="Retry printed OCR runtime initialization",
    responses={
        400: {"model": ApiErrorEnvelope, "description": "OCR retry is not allowed."},
        409: {"model": ApiErrorEnvelope, "description": "OCR initialization already running."},
        503: {"model": ApiErrorEnvelope, "description": "OCR runtime is unavailable."},
    },
)
async def retry_ocr_runtime(request: Request) -> OcrRetryAcceptedResponse:
    """Start or rejoin OCR worker initialization without restarting the API process."""

    settings = _settings(request)
    manager = _ocr_manager(request)
    if not settings.ocr_enabled:
        raise ApiException(
            status_code=400,
            code=ErrorCode.OCR_RETRY_NOT_ALLOWED,
            message="Printed OCR is disabled.",
            details={
                "retryable": False,
                "error_code": "ocr_disabled",
                "operator_hint": (
                    "Enable OCR in settings (OCR_ENABLED=true) if printed OCR is required."
                ),
            },
        )
    if manager is None:
        raise ApiException(
            status_code=503,
            code=ErrorCode.OCR_RUNTIME_UNAVAILABLE,
            message="Printed OCR runtime is unavailable.",
            details={"retryable": False, "error_code": "ocr_unknown_failure"},
        )

    before = manager.runtime_status()
    if before.ready:
        return OcrRetryAcceptedResponse(
            attempt_id=before.attempt_id or "ready",
            state=before.state,
            stage=before.stage,
        )

    if before.restart_required or (
        before.state is OcrRuntimeState.FAILED
        and before.error_code is not None
        and not is_retryable(before.error_code, restart_required=before.restart_required)
    ):
        raise ApiException(
            status_code=400,
            code=ErrorCode.OCR_RETRY_NOT_ALLOWED,
            message=before.user_message or "Printed OCR retry is not allowed.",
            details={
                "retryable": False,
                "restart_required": before.restart_required,
                "recovery_action": before.recovery_action.value,
                "error_code": before.error_code.value if before.error_code else None,
                "operator_hint": before.operator_hint,
                "technical_detail": before.technical_detail,
                "attempt_number": before.attempt_number,
            },
        )

    if manager.initialization_running or before.state in {
        OcrRuntimeState.STARTING,
        OcrRuntimeState.LOADING_DETECTOR,
        OcrRuntimeState.LOADING_RECOGNIZER,
        OcrRuntimeState.WARMING_UP,
    }:
        # Prefer returning the current attempt (202) over a hard conflict.
        return OcrRetryAcceptedResponse(
            attempt_id=before.attempt_id or "in_progress",
            state=before.state,
            stage=before.stage,
        )

    status_after = await manager.retry_initialization()
    attempt_id = status_after.attempt_id or before.attempt_id or "retry"
    return OcrRetryAcceptedResponse(
        attempt_id=attempt_id,
        state=status_after.state,
        stage=status_after.stage,
    )

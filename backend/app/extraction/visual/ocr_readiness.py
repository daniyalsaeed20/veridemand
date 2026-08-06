"""Map OCR startup failures to safe, stable readiness codes and copy."""

from __future__ import annotations

import re
from typing import Any

from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.ocr_runtime import OcrRecoveryAction, OcrRuntimeErrorCode
from backend.app.extraction.visual.ocr_environment import (
    OcrEnvironmentDiagnostics,
    dll_failure_requires_restart,
    probe_ocr_environment,
)

_PATH_RE = re.compile(r"(?:[A-Za-z]:\\|/)[^\s'\"]+")
_SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*\S+")

_RESTART_OCR_HINT = (
    "Stop this backend and restart VeriDemand using the OCR-only environment (pnpm dev:ocr)."
)


def sanitize_technical_detail(raw: str | None, *, max_len: int = 240) -> str | None:
    """Return a short technical summary with paths/secrets stripped."""

    if not raw:
        return None
    text = " ".join(str(raw).split())
    text = _PATH_RE.sub("<path>", text)
    text = _SECRET_RE.sub(r"\1=<redacted>", text)
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text or None


def is_retryable(code: OcrRuntimeErrorCode, *, restart_required: bool = False) -> bool:
    """Return whether an in-process Retry OCR action is allowed."""

    if restart_required:
        return False
    return code in {
        # Transient DLL load inside a clean .venv-ocr only (restart_required=False).
        OcrRuntimeErrorCode.OCR_DLL_LOAD_FAILED,
        OcrRuntimeErrorCode.OCR_DETECTOR_LOAD_FAILED,
        OcrRuntimeErrorCode.OCR_RECOGNIZER_LOAD_FAILED,
        OcrRuntimeErrorCode.OCR_WARMUP_FAILED,
        OcrRuntimeErrorCode.OCR_STARTUP_TIMEOUT,
        OcrRuntimeErrorCode.OCR_OUT_OF_MEMORY,
        OcrRuntimeErrorCode.OCR_UNKNOWN_FAILURE,
        OcrRuntimeErrorCode.OCR_INITIALIZATION_ALREADY_RUNNING,
    }


def restart_required_for(
    code: OcrRuntimeErrorCode,
    *,
    technical_detail: str | None = None,
    diagnostics: OcrEnvironmentDiagnostics | None = None,
) -> bool:
    """Decide whether the current failure requires an OS-process restart."""

    env = diagnostics or probe_ocr_environment()
    if code is OcrRuntimeErrorCode.OCR_DLL_LOAD_FAILED:
        return dll_failure_requires_restart(env, technical_detail=technical_detail)
    if code is OcrRuntimeErrorCode.OCR_DEPENDENCY_IMPORT_FAILED and env.environment_conflict:
        return True
    return bool(
        env.environment_conflict
        and code
        in {
            OcrRuntimeErrorCode.OCR_DETECTOR_LOAD_FAILED,
            OcrRuntimeErrorCode.OCR_RECOGNIZER_LOAD_FAILED,
            OcrRuntimeErrorCode.OCR_UNKNOWN_FAILURE,
        }
    )


def recovery_action_for(
    code: OcrRuntimeErrorCode,
    *,
    restart_required: bool,
    retryable: bool,
) -> OcrRecoveryAction:
    if restart_required:
        return OcrRecoveryAction.RESTART_BACKEND_IN_OCR_ENVIRONMENT
    if retryable and code is not OcrRuntimeErrorCode.OCR_DISABLED:
        return OcrRecoveryAction.RETRY_OCR_RUNTIME
    return OcrRecoveryAction.NONE


def user_message_for(code: OcrRuntimeErrorCode, *, restart_required: bool = False) -> str:
    if restart_required and code in {
        OcrRuntimeErrorCode.OCR_DLL_LOAD_FAILED,
        OcrRuntimeErrorCode.OCR_DEPENDENCY_IMPORT_FAILED,
    }:
        return "Printed OCR cannot load in the current backend environment."
    messages: dict[OcrRuntimeErrorCode, str] = {
        OcrRuntimeErrorCode.OCR_DISABLED: "Printed OCR is disabled.",
        OcrRuntimeErrorCode.OCR_CONFIGURATION_INVALID: ("Printed OCR configuration is invalid."),
        OcrRuntimeErrorCode.OCR_MODELS_MISSING: (
            "Printed OCR model files are missing or incomplete."
        ),
        OcrRuntimeErrorCode.OCR_MODEL_INTEGRITY_FAILED: (
            "Printed OCR model files failed integrity verification."
        ),
        OcrRuntimeErrorCode.OCR_DEPENDENCY_IMPORT_FAILED: (
            "Printed OCR Python dependencies could not be imported."
        ),
        OcrRuntimeErrorCode.OCR_DLL_LOAD_FAILED: ("Printed OCR dependency failed to load."),
        OcrRuntimeErrorCode.OCR_DETECTOR_LOAD_FAILED: ("Printed OCR detector failed to load."),
        OcrRuntimeErrorCode.OCR_RECOGNIZER_LOAD_FAILED: ("Printed OCR recognizer failed to load."),
        OcrRuntimeErrorCode.OCR_WARMUP_FAILED: ("Printed OCR warm-up failed."),
        OcrRuntimeErrorCode.OCR_STARTUP_TIMEOUT: ("Printed OCR startup timed out."),
        OcrRuntimeErrorCode.OCR_OUT_OF_MEMORY: ("Printed OCR ran out of memory while starting."),
        OcrRuntimeErrorCode.OCR_INITIALIZATION_ALREADY_RUNNING: (
            "Printed OCR initialization is already running."
        ),
        OcrRuntimeErrorCode.OCR_UNKNOWN_FAILURE: ("Printed OCR could not start."),
        OcrRuntimeErrorCode.BACKEND_UNREACHABLE: ("Backend connection unavailable."),
    }
    return messages[code]


def operator_hint_for(code: OcrRuntimeErrorCode, *, restart_required: bool = False) -> str:
    if restart_required:
        return _RESTART_OCR_HINT
    hints: dict[OcrRuntimeErrorCode, str] = {
        OcrRuntimeErrorCode.OCR_DISABLED: (
            "Enable OCR in settings (OCR_ENABLED=true) if printed OCR is required."
        ),
        OcrRuntimeErrorCode.OCR_CONFIGURATION_INVALID: (
            "Correct OCR settings, then restart the API process and retry OCR."
        ),
        OcrRuntimeErrorCode.OCR_MODELS_MISSING: (
            "Bootstrap local OCR models with the approved models:ocr:bootstrap command, then retry."
        ),
        OcrRuntimeErrorCode.OCR_MODEL_INTEGRITY_FAILED: (
            "Re-bootstrap OCR models so model-record.json matches the local "
            "tree hashes, then retry."
        ),
        OcrRuntimeErrorCode.OCR_DEPENDENCY_IMPORT_FAILED: (
            "Install the OCR dependency group in the OCR-only environment (.venv-ocr), then retry."
        ),
        OcrRuntimeErrorCode.OCR_DLL_LOAD_FAILED: (
            "Retry OCR. If the native library error persists in the OCR-only environment, "
            "check server logs."
        ),
        OcrRuntimeErrorCode.OCR_DETECTOR_LOAD_FAILED: (
            "Confirm detector model files are present and retry OCR. "
            "If it persists, check server logs."
        ),
        OcrRuntimeErrorCode.OCR_RECOGNIZER_LOAD_FAILED: (
            "Confirm recognizer model files are present and retry OCR. "
            "If it persists, check server logs."
        ),
        OcrRuntimeErrorCode.OCR_WARMUP_FAILED: (
            "Retry OCR. If warm-up keeps failing, verify the OCR-only environment and free memory."
        ),
        OcrRuntimeErrorCode.OCR_STARTUP_TIMEOUT: (
            "Retry OCR. Large model loads can take time; "
            "if timeouts persist, check CPU load and logs."
        ),
        OcrRuntimeErrorCode.OCR_OUT_OF_MEMORY: (
            "Free memory or reduce concurrent workloads, then retry OCR."
        ),
        OcrRuntimeErrorCode.OCR_INITIALIZATION_ALREADY_RUNNING: (
            "Wait for the current OCR startup attempt to finish."
        ),
        OcrRuntimeErrorCode.OCR_UNKNOWN_FAILURE: (
            "Retry OCR. If it fails again, check server logs for the sanitized failure detail."
        ),
        OcrRuntimeErrorCode.BACKEND_UNREACHABLE: (
            "Confirm the VeriDemand backend process is running and reachable, "
            "then check connection."
        ),
    }
    return hints[code]


def classify_exception(
    exc: BaseException,
    *,
    operation: str | None = None,
    legacy_code: ErrorCode | str | None = None,
) -> tuple[OcrRuntimeErrorCode, str | None]:
    """Map an exception (and optional legacy OCR code) to a readiness error code."""

    message = str(exc)
    lowered = message.lower()
    exc_name = type(exc).__name__
    detail = sanitize_technical_detail(f"{exc_name}: {message}")

    if isinstance(exc, MemoryError) or "out of memory" in lowered or re.search(r"\boom\b", lowered):
        return OcrRuntimeErrorCode.OCR_OUT_OF_MEMORY, detail

    if any(
        token in lowered
        for token in ("shm.dll", "dll load failed", "winerror 126", "winerror 127", "c10.dll")
    ) or ("torch" in lowered and ("dll" in lowered or "load" in lowered)):
        return OcrRuntimeErrorCode.OCR_DLL_LOAD_FAILED, detail

    if isinstance(exc, ImportError) or operation == "import_paddle":
        return OcrRuntimeErrorCode.OCR_DEPENDENCY_IMPORT_FAILED, detail

    if isinstance(exc, FileNotFoundError) or operation == "resolve_model_dirs":
        return OcrRuntimeErrorCode.OCR_MODELS_MISSING, detail

    if "tree hash" in lowered or "integrity" in lowered or "model-record" in lowered:
        return OcrRuntimeErrorCode.OCR_MODEL_INTEGRITY_FAILED, detail

    if operation == "warmup" or "warm-up" in lowered or "warmup" in lowered:
        return OcrRuntimeErrorCode.OCR_WARMUP_FAILED, detail

    if operation in {"paddleocr_init", "load_detector"} or "detector" in lowered:
        if "recognizer" in lowered or "recognition" in lowered:
            return OcrRuntimeErrorCode.OCR_RECOGNIZER_LOAD_FAILED, detail
        return OcrRuntimeErrorCode.OCR_DETECTOR_LOAD_FAILED, detail

    if operation == "load_recognizer":
        return OcrRuntimeErrorCode.OCR_RECOGNIZER_LOAD_FAILED, detail

    if operation == "await_ready" and "timed out" in lowered:
        return OcrRuntimeErrorCode.OCR_STARTUP_TIMEOUT, detail

    legacy = legacy_code.value if isinstance(legacy_code, ErrorCode) else legacy_code
    if legacy == ErrorCode.OCR_MODEL_NOT_FOUND.value:
        return OcrRuntimeErrorCode.OCR_MODELS_MISSING, detail
    if legacy == ErrorCode.OCR_RUNTIME_UNAVAILABLE.value:
        return OcrRuntimeErrorCode.OCR_DEPENDENCY_IMPORT_FAILED, detail
    if legacy == ErrorCode.OCR_MODEL_LOAD_FAILED.value:
        if operation == "warmup":
            return OcrRuntimeErrorCode.OCR_WARMUP_FAILED, detail
        return OcrRuntimeErrorCode.OCR_DETECTOR_LOAD_FAILED, detail
    if legacy == ErrorCode.OCR_WORKER_START_FAILED.value and "timed out" in lowered:
        return OcrRuntimeErrorCode.OCR_STARTUP_TIMEOUT, detail

    return OcrRuntimeErrorCode.OCR_UNKNOWN_FAILURE, detail


def classify_worker_failure_payload(
    message: dict[str, Any],
) -> tuple[OcrRuntimeErrorCode, str | None]:
    """Classify a worker NDJSON failure payload without trusting free-form text."""

    code_raw = str(message.get("error_code") or message.get("code") or "")
    try:
        if code_raw in {item.value for item in OcrRuntimeErrorCode}:
            code = OcrRuntimeErrorCode(code_raw)
            detail = sanitize_technical_detail(
                str(message.get("technical_detail") or message.get("exception_type") or code_raw)
            )
            return code, detail
    except ValueError:
        pass

    operation = str(message.get("operation") or "") or None
    exception_type = str(message.get("exception_type") or "Exception")
    synthetic = Exception(f"{exception_type}")
    return classify_exception(synthetic, operation=operation, legacy_code=code_raw or None)

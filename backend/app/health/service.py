"""Health service: evaluates Phase 0-5 readiness checks.

Phase 4 promotes PaddleOCR to a required check when OCR_ENABLED is true, and
always requires pypdfium2 for page rendering. Phase 5 handwriting classifier
readiness follows ``handwriting_router_enabled`` /
``handwriting_classifier_required``. OpenAI remains an optional
``not_configured`` stub (Phase 6).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from backend.app.canonical.libreoffice import LibreOfficeService
from backend.app.contracts.health import CheckState, DependencyCheck, HealthState
from backend.app.contracts.ocr_runtime import OcrRuntimeStatus
from backend.app.settings.config import Settings
from backend.app.storage import paths

_PROBE_FILENAME = ".readiness_probe"
_SESSION_PROBE_DIRNAME = ".workspace_probe"
_CANONICAL_PROBE_DIRNAME = ".canonical_probe"

_FUTURE_OPTIONAL_CHECKS: tuple[str, ...] = ("openai_vision",)


class _Runnable(Protocol):
    @property
    def running(self) -> bool: ...


class _Closable(Protocol):
    @property
    def closed(self) -> bool: ...


class _OcrWorkerReady(Protocol):
    @property
    def ready(self) -> bool: ...

    def runtime_status(self) -> object: ...


class HealthService:
    """Computes liveness and readiness from settings and runtime components."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._coordinator: _Runnable | None = None
        self._cleanup_worker: _Runnable | None = None
        self._job_queue: _Closable | None = None
        self._libreoffice = LibreOfficeService(settings)
        self._cached_libreoffice: DependencyCheck | None = None
        self._cached_reportlab: DependencyCheck | None = None
        self._cached_pdfplumber: DependencyCheck | None = None
        self._cached_native_worker: DependencyCheck | None = None
        self._cached_native_storage: DependencyCheck | None = None
        self._cached_native_policy: DependencyCheck | None = None
        self._ocr_worker_manager: _OcrWorkerReady | None = None
        self._cached_paddle: DependencyCheck | None = None
        self._cached_pypdfium2: DependencyCheck | None = None
        self._cached_visual_storage: DependencyCheck | None = None

    def attach_runtime(
        self,
        *,
        coordinator: _Runnable,
        cleanup_worker: _Runnable,
        job_queue: _Closable,
        ocr_worker_manager: _OcrWorkerReady | None = None,
    ) -> None:
        """Bind runtime components started during application lifespan."""

        self._coordinator = coordinator
        self._cleanup_worker = cleanup_worker
        self._job_queue = job_queue
        self._ocr_worker_manager = ocr_worker_manager

    def _check_settings(self) -> DependencyCheck:
        return DependencyCheck(
            name="settings",
            status=CheckState.PASS,
            required=True,
            message="Application settings loaded and validated.",
        )

    def _check_temp_storage(self) -> DependencyCheck:
        temp_root = self._settings.temp_root
        try:
            temp_root.mkdir(parents=True, exist_ok=True)
            probe = temp_root / _PROBE_FILENAME
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError:
            return DependencyCheck(
                name="temp_storage",
                status=CheckState.FAIL,
                required=True,
                message="Temporary storage is not writable.",
            )
        return DependencyCheck(
            name="temp_storage",
            status=CheckState.PASS,
            required=True,
            message="Temporary storage exists and is writable.",
        )

    def _check_session_workspace(self) -> DependencyCheck:
        root = paths.sessions_root(self._settings.temp_root)
        try:
            root.mkdir(parents=True, exist_ok=True)
            probe = root / _SESSION_PROBE_DIRNAME
            probe.mkdir(exist_ok=True)
            probe.rmdir()
        except OSError:
            return DependencyCheck(
                name="session_workspace",
                status=CheckState.FAIL,
                required=True,
                message="Session workspace is not writable.",
            )
        return DependencyCheck(
            name="session_workspace",
            status=CheckState.PASS,
            required=True,
            message="Session workspace exists and is writable.",
        )

    def _check_canonical_storage(self) -> DependencyCheck:
        root = paths.sessions_root(self._settings.temp_root)
        try:
            root.mkdir(parents=True, exist_ok=True)
            probe = root / _CANONICAL_PROBE_DIRNAME
            probe.mkdir(exist_ok=True)
            (probe / "canonical").mkdir(exist_ok=True)
            (probe / "canonical").rmdir()
            probe.rmdir()
        except OSError:
            return DependencyCheck(
                name="canonical_storage",
                status=CheckState.FAIL,
                required=True,
                message="Canonical storage is not writable.",
            )
        return DependencyCheck(
            name="canonical_storage",
            status=CheckState.PASS,
            required=True,
            message="Canonical storage can be created and deleted.",
        )

    def _check_coordinator(self) -> DependencyCheck:
        healthy = self._coordinator is not None and self._coordinator.running
        return DependencyCheck(
            name="processing_coordinator",
            status=CheckState.PASS if healthy else CheckState.FAIL,
            required=True,
            message=(
                "Canonicalisation coordinator is running."
                if healthy
                else "Canonicalisation coordinator is not running."
            ),
        )

    def _check_cleanup(self) -> DependencyCheck:
        healthy = self._cleanup_worker is not None and self._cleanup_worker.running
        return DependencyCheck(
            name="cleanup_worker",
            status=CheckState.PASS if healthy else CheckState.FAIL,
            required=True,
            message=("Cleanup worker is running." if healthy else "Cleanup worker is not running."),
        )

    def _check_queue(self) -> DependencyCheck:
        healthy = self._job_queue is not None and not self._job_queue.closed
        return DependencyCheck(
            name="processing_queue",
            status=CheckState.PASS if healthy else CheckState.FAIL,
            required=True,
            message=(
                "Processing queue is accepting work."
                if healthy
                else "Processing queue is not accepting work."
            ),
        )

    def _check_libreoffice(self) -> DependencyCheck:
        if self._cached_libreoffice is not None:
            return self._cached_libreoffice
        try:
            runtime = self._libreoffice.resolve()
            check = DependencyCheck(
                name="libreoffice",
                status=CheckState.PASS,
                required=True,
                message=f"LibreOffice available ({runtime.version}).",
            )
        except Exception:
            check = DependencyCheck(
                name="libreoffice",
                status=CheckState.FAIL,
                required=True,
                message="LibreOffice is missing or unusable.",
            )
        self._cached_libreoffice = check
        return check

    def _check_reportlab(self) -> DependencyCheck:
        if self._cached_reportlab is not None:
            return self._cached_reportlab
        try:
            from reportlab.pdfbase.pdfmetrics import getFont

            getFont("Helvetica")
            check = DependencyCheck(
                name="reportlab",
                status=CheckState.PASS,
                required=True,
                message="ReportLab import succeeds and Helvetica is available.",
            )
        except Exception:
            check = DependencyCheck(
                name="reportlab",
                status=CheckState.FAIL,
                required=True,
                message="ReportLab or controlled font is unavailable.",
            )
        self._cached_reportlab = check
        return check

    def _check_pdfplumber(self) -> DependencyCheck:
        if self._cached_pdfplumber is not None:
            return self._cached_pdfplumber
        try:
            import pdfplumber  # noqa: F401

            check = DependencyCheck(
                name="pdfplumber",
                status=CheckState.PASS,
                required=True,
                message="pdfplumber import succeeds.",
            )
        except Exception:
            check = DependencyCheck(
                name="pdfplumber",
                status=CheckState.FAIL,
                required=True,
                message="pdfplumber cannot be imported.",
            )
        self._cached_pdfplumber = check
        return check

    def _check_native_policy(self) -> DependencyCheck:
        if self._cached_native_policy is not None:
            return self._cached_native_policy
        try:
            # Instantiating Settings already validates; re-check key invariants.
            assert self._settings.native_workers == 1
            assert self._settings.native_trust_policy_version.strip()
            assert (
                self._settings.native_termination_grace_seconds
                < self._settings.native_extraction_timeout_seconds
            )
            check = DependencyCheck(
                name="native_trust_policy",
                status=CheckState.PASS,
                required=True,
                message="Native trust policy configuration is valid.",
            )
        except Exception:
            check = DependencyCheck(
                name="native_trust_policy",
                status=CheckState.FAIL,
                required=True,
                message="Native trust policy configuration is invalid.",
            )
        self._cached_native_policy = check
        return check

    def _check_native_storage(self) -> DependencyCheck:
        if self._cached_native_storage is not None:
            return self._cached_native_storage
        root = paths.sessions_root(self._settings.temp_root)
        try:
            root.mkdir(parents=True, exist_ok=True)
            probe = root / ".native_probe"
            probe.mkdir(exist_ok=True)
            staging = probe / "staging" / "native"
            results = probe / "results" / "native"
            staging.mkdir(parents=True, exist_ok=True)
            results.mkdir(parents=True, exist_ok=True)
            staging.rmdir()
            results.rmdir()
            (probe / "staging").rmdir()
            (probe / "results").rmdir()
            probe.rmdir()
            check = DependencyCheck(
                name="native_result_storage",
                status=CheckState.PASS,
                required=True,
                message="Native result staging can be created and deleted.",
            )
        except OSError:
            check = DependencyCheck(
                name="native_result_storage",
                status=CheckState.FAIL,
                required=True,
                message="Native result storage is not writable.",
            )
        self._cached_native_storage = check
        return check

    def _check_native_worker(self) -> DependencyCheck:
        if self._cached_native_worker is not None:
            return self._cached_native_worker
        import json
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        from backend.app.extraction.native.models import (
            NativeTrustPolicyConfig,
            NativeWorkerRequest,
        )

        try:
            with tempfile.TemporaryDirectory(prefix="vd-native-selfcheck-") as tmp:
                staging = Path(tmp)
                request = NativeWorkerRequest(
                    session_id="ses_" + ("0" * 32),
                    document_id="doc_" + ("0" * 32),
                    job_id="job_" + ("0" * 32),
                    canonical_pdf_path="",
                    canonicalisation_method="original_pdf",
                    pages=[],
                    policy=NativeTrustPolicyConfig(),
                    self_check=True,
                )
                request_path = staging / "request.json"
                output_path = staging / "result.json.part"
                request_path.write_text(
                    json.dumps(request.to_dict(), separators=(",", ":")), encoding="utf-8"
                )
                repo_root = str(Path(__file__).resolve().parents[3])
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "backend.app.extraction.native.worker",
                        "--request",
                        str(request_path),
                        "--output",
                        str(output_path),
                    ],
                    check=False,
                    capture_output=True,
                    timeout=30,
                    cwd=repo_root,
                    env={**dict(**__import__("os").environ), "PYTHONPATH": repo_root},
                )
                ok = completed.returncode == 0 and output_path.is_file()
            check = DependencyCheck(
                name="native_worker",
                status=CheckState.PASS if ok else CheckState.FAIL,
                required=True,
                message=(
                    "Native worker self-check succeeded."
                    if ok
                    else "Native worker self-check failed."
                ),
            )
        except Exception:
            check = DependencyCheck(
                name="native_worker",
                status=CheckState.FAIL,
                required=True,
                message="Native worker self-check failed.",
            )
        self._cached_native_worker = check
        return check

    @staticmethod
    def _future_checks() -> list[DependencyCheck]:
        return [
            DependencyCheck(
                name=name,
                status=CheckState.NOT_CONFIGURED,
                required=False,
                message="Not enabled yet.",
            )
            for name in _FUTURE_OPTIONAL_CHECKS
        ]

    def _check_handwriting_classifier(self) -> DependencyCheck:
        """Report handwriting classifier readiness without leaking filesystem paths."""

        if not self._settings.handwriting_router_enabled:
            return DependencyCheck(
                name="handwriting_classifier",
                status=CheckState.NOT_CONFIGURED,
                required=False,
                message="Handwriting router disabled.",
            )

        required = bool(self._settings.handwriting_classifier_required)
        # Lazy import keeps optional tooling boundaries clear for health.
        from backend.app.extraction.handwriting_router.service import (
            HandwritingClassifierService,
        )
        from backend.app.extraction.handwriting_router.verifier import (
            VerificationFailureCode,
        )

        service = HandwritingClassifierService(self._settings)
        result = service.verify_package(allow_test_fixture=False)
        if result.ready:
            version = result.model_version or "unknown"
            thr = result.threshold_set_version or "unknown"
            status_label = (
                result.package_status.value if result.package_status is not None else "unknown"
            )
            return DependencyCheck(
                name="handwriting_classifier",
                status=CheckState.PASS,
                required=required,
                message=(
                    f"Classifier ready (model={version}, thresholds={thr}, "
                    f"status={status_label}, provider={result.runtime_provider})."
                ),
            )

        code = result.failure_code or VerificationFailureCode.PACKAGE_DIR_MISSING
        # Map failure codes to short non-sensitive messages (no absolute paths).
        detail = result.message
        return DependencyCheck(
            name="handwriting_classifier",
            status=CheckState.FAIL,
            required=required,
            message=f"Classifier not ready ({code.value}): {detail}",
        )

    def _check_pypdfium2(self) -> DependencyCheck:
        if self._cached_pypdfium2 is not None:
            return self._cached_pypdfium2
        try:
            import pypdfium2  # noqa: F401
        except ImportError:
            check = DependencyCheck(
                name="pypdfium2",
                status=CheckState.FAIL,
                required=True,
                message="pypdfium2 is not importable.",
            )
        else:
            check = DependencyCheck(
                name="pypdfium2",
                status=CheckState.PASS,
                required=True,
                message="pypdfium2 is available for page rendering.",
            )
        self._cached_pypdfium2 = check
        return check

    def _check_visual_storage(self) -> DependencyCheck:
        if self._cached_visual_storage is not None:
            return self._cached_visual_storage
        root = self._settings.temp_root / "sessions"
        try:
            root.mkdir(parents=True, exist_ok=True)
            probe_dir = root / ".visual_probe"
            probe_dir.mkdir(parents=True, exist_ok=True)
            probe = probe_dir / "probe.json"
            probe.write_text("{}", encoding="utf-8")
            probe.unlink()
            probe_dir.rmdir()
        except OSError:
            check = DependencyCheck(
                name="visual_result_storage",
                status=CheckState.FAIL,
                required=True,
                message="Visual result storage is not writable.",
            )
        else:
            check = DependencyCheck(
                name="visual_result_storage",
                status=CheckState.PASS,
                required=True,
                message="Visual result storage is writable.",
            )
        self._cached_visual_storage = check
        return check

    def _check_paddle_ocr(self) -> DependencyCheck:
        if not self._settings.ocr_enabled:
            return DependencyCheck(
                name="paddle_ocr",
                status=CheckState.NOT_CONFIGURED,
                required=False,
                message="OCR is disabled.",
            )
        if self._cached_paddle is not None:
            # Still refresh worker-alive portion.
            pass
        try:
            import paddle  # noqa: F401
            import paddleocr  # noqa: F401
        except ImportError:
            return DependencyCheck(
                name="paddle_ocr",
                status=CheckState.FAIL,
                required=True,
                message="PaddleOCR runtime is not installed.",
            )

        model_root = self._settings.ocr_model_root
        record_path = model_root / "model-record.json"
        det = model_root / self._settings.ocr_detection_model_name
        rec = model_root / self._settings.ocr_recognition_model_name
        det_empty = det.is_dir() and not any(det.iterdir())
        rec_empty = rec.is_dir() and not any(rec.iterdir())
        if (
            not record_path.is_file()
            or not det.is_dir()
            or not rec.is_dir()
            or det_empty
            or rec_empty
        ):
            return DependencyCheck(
                name="paddle_ocr",
                status=CheckState.FAIL,
                required=True,
                message="OCR model directories are missing, empty, or model-record.json is absent.",
            )

        try:
            import hashlib
            import json
            from pathlib import Path

            record = json.loads(record_path.read_text(encoding="utf-8"))

            def _tree_hash(directory: Path) -> str:
                digest = hashlib.sha256()
                for path in sorted(directory.rglob("*")):
                    if path.is_file():
                        rel = path.relative_to(directory).as_posix().encode("utf-8")
                        digest.update(rel)
                        digest.update(b"\0")
                        with path.open("rb") as handle:
                            while True:
                                chunk = handle.read(1024 * 1024)
                                if not chunk:
                                    break
                                digest.update(chunk)
                return digest.hexdigest()

            if _tree_hash(det) != record.get("detection_tree_hash"):
                return DependencyCheck(
                    name="paddle_ocr",
                    status=CheckState.FAIL,
                    required=True,
                    message="Detection model tree hash does not match model-record.json.",
                )
            if _tree_hash(rec) != record.get("recognition_tree_hash"):
                return DependencyCheck(
                    name="paddle_ocr",
                    status=CheckState.FAIL,
                    required=True,
                    message="Recognition model tree hash does not match model-record.json.",
                )
        except Exception:
            return DependencyCheck(
                name="paddle_ocr",
                status=CheckState.FAIL,
                required=True,
                message="OCR model-record.json could not be validated.",
            )

        worker = self._ocr_worker_manager
        ready = bool(worker is not None and worker.ready)
        if not ready:
            message = "OCR worker is not ready."
            if worker is not None:
                status = worker.runtime_status()
                if isinstance(status, OcrRuntimeStatus) and status.user_message:
                    message = status.user_message
            return DependencyCheck(
                name="paddle_ocr",
                status=CheckState.FAIL,
                required=True,
                message=message,
            )
        check = DependencyCheck(
            name="paddle_ocr",
            status=CheckState.PASS,
            required=True,
            message="PaddleOCR models and worker are ready.",
        )
        self._cached_paddle = check
        return check

    def readiness_checks(self) -> list[DependencyCheck]:
        """Run all readiness checks and return them in a stable order."""

        checks = [
            self._check_settings(),
            self._check_temp_storage(),
            self._check_session_workspace(),
            self._check_canonical_storage(),
            self._check_native_storage(),
            self._check_visual_storage(),
            self._check_coordinator(),
            self._check_cleanup(),
            self._check_queue(),
            self._check_libreoffice(),
            self._check_reportlab(),
            self._check_pdfplumber(),
            self._check_pypdfium2(),
            self._check_native_policy(),
            self._check_native_worker(),
            self._check_paddle_ocr(),
            self._check_handwriting_classifier(),
        ]
        checks.extend(self._future_checks())
        return checks

    def ocr_runtime_status(self) -> OcrRuntimeStatus | None:
        """Return structured OCR readiness when a worker manager is attached."""

        worker = self._ocr_worker_manager
        if worker is None:
            if not self._settings.ocr_enabled:
                from backend.app.contracts.ocr_runtime import (
                    OcrComponentStatus,
                    OcrRuntimeErrorCode,
                    OcrRuntimeState,
                )
                from backend.app.extraction.visual.ocr_readiness import (
                    operator_hint_for,
                    user_message_for,
                )

                return OcrRuntimeStatus(
                    state=OcrRuntimeState.DISABLED,
                    ready=False,
                    retryable=False,
                    error_code=OcrRuntimeErrorCode.OCR_DISABLED,
                    user_message=user_message_for(OcrRuntimeErrorCode.OCR_DISABLED),
                    operator_hint=operator_hint_for(OcrRuntimeErrorCode.OCR_DISABLED),
                    detector_status=OcrComponentStatus.NOT_APPLICABLE,
                    recognizer_status=OcrComponentStatus.NOT_APPLICABLE,
                    model_verification_status=OcrComponentStatus.NOT_APPLICABLE,
                )
            return None
        status = worker.runtime_status()
        assert isinstance(status, OcrRuntimeStatus)
        return status

    @staticmethod
    def overall_state(checks: Sequence[DependencyCheck]) -> HealthState:
        """Aggregate checks into an overall readiness state."""

        if any(check.required and check.status == CheckState.FAIL for check in checks):
            return HealthState.NOT_READY
        return HealthState.READY

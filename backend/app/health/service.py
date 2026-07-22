"""Health service: evaluates Phase 0-2 readiness checks.

Phase 2 requires LibreOffice, ReportLab (with a controlled font), writable
canonical storage, plus the Phase 1 session/coordinator/cleanup/queue checks.
OCR and OpenAI remain optional ``not_configured`` checks.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from backend.app.canonical.libreoffice import LibreOfficeService
from backend.app.contracts.health import CheckState, DependencyCheck, HealthState
from backend.app.settings.config import Settings
from backend.app.storage import paths

_PROBE_FILENAME = ".readiness_probe"
_SESSION_PROBE_DIRNAME = ".workspace_probe"
_CANONICAL_PROBE_DIRNAME = ".canonical_probe"

_FUTURE_OPTIONAL_CHECKS: tuple[str, ...] = (
    "paddle_ocr",
    "handwriting_classifier",
    "openai_vision",
)


class _Runnable(Protocol):
    @property
    def running(self) -> bool: ...


class _Closable(Protocol):
    @property
    def closed(self) -> bool: ...


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

    def attach_runtime(
        self,
        *,
        coordinator: _Runnable,
        cleanup_worker: _Runnable,
        job_queue: _Closable,
    ) -> None:
        """Bind runtime components started during application lifespan."""

        self._coordinator = coordinator
        self._cleanup_worker = cleanup_worker
        self._job_queue = job_queue

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

    def readiness_checks(self) -> list[DependencyCheck]:
        """Run all readiness checks and return them in a stable order."""

        checks = [
            self._check_settings(),
            self._check_temp_storage(),
            self._check_session_workspace(),
            self._check_canonical_storage(),
            self._check_coordinator(),
            self._check_cleanup(),
            self._check_queue(),
            self._check_libreoffice(),
            self._check_reportlab(),
        ]
        checks.extend(self._future_checks())
        return checks

    @staticmethod
    def overall_state(checks: Sequence[DependencyCheck]) -> HealthState:
        """Aggregate checks into an overall readiness state."""

        if any(check.required and check.status == CheckState.FAIL for check in checks):
            return HealthState.NOT_READY
        return HealthState.READY

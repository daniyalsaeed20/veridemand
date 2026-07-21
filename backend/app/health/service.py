"""Health service: evaluates Phase 0 readiness checks.

Phase 0 only verifies that settings loaded and that the temporary workspace is
usable. Future capabilities (LibreOffice, PaddleOCR, the handwriting classifier
and the vision provider) are reported as optional ``not_configured`` checks and
never make the service unready. Later phases will promote them to real checks.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.app.contracts.health import CheckState, DependencyCheck, HealthState
from backend.app.settings.config import Settings

_PROBE_FILENAME = ".readiness_probe"

# Optional future dependencies, surfaced for visibility but not required yet.
_FUTURE_OPTIONAL_CHECKS: tuple[str, ...] = (
    "libreoffice",
    "paddle_ocr",
    "handwriting_classifier",
    "openai_vision",
)


class HealthService:
    """Computes liveness and readiness from the active settings."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

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

    @staticmethod
    def _future_checks() -> list[DependencyCheck]:
        return [
            DependencyCheck(
                name=name,
                status=CheckState.NOT_CONFIGURED,
                required=False,
                message="Not enabled in Phase 0.",
            )
            for name in _FUTURE_OPTIONAL_CHECKS
        ]

    def readiness_checks(self) -> list[DependencyCheck]:
        """Run all readiness checks and return them in a stable order."""

        checks = [self._check_settings(), self._check_temp_storage()]
        checks.extend(self._future_checks())
        return checks

    @staticmethod
    def overall_state(checks: Sequence[DependencyCheck]) -> HealthState:
        """Aggregate checks into an overall readiness state."""

        if any(check.required and check.status == CheckState.FAIL for check in checks):
            return HealthState.NOT_READY
        return HealthState.READY

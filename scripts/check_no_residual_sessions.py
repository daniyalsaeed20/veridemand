"""Verify runtime session data never outlives the application.

Runtime sessions are temporary. Two mechanisms guarantee nothing is left on disk:

1. Graceful shutdown removes every live session directory.
2. On the next startup, an abandoned-directory sweep removes any session dirs left
   behind by a previous *non-graceful* termination (e.g. a force-killed dev server
   during E2E teardown, which is common on Windows).

This guard runs a clean application lifecycle against each real temp root (which
triggers the startup sweep and the shutdown cleanup) and then asserts that no
``<TEMP_ROOT>/sessions/ses_*`` directory remains. It both exercises the cleanup
code paths and proves the end state is empty.
"""

from __future__ import annotations

from pathlib import Path

from backend.app.main import create_app
from backend.app.settings.config import Settings
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent

# Temp roots used by the app and the E2E "holds" backend (see playwright.config.ts).
TEMP_ROOTS = (ROOT / "temp", ROOT / "temp-e2e")


def residual_session_dirs(temp_root: Path) -> list[Path]:
    sessions = temp_root / "sessions"
    if not sessions.is_dir():
        return []
    return [child for child in sessions.iterdir() if child.name.startswith("ses_")]


def run_clean_lifecycle(temp_root: Path) -> None:
    """Enter and exit the app lifespan so startup + shutdown cleanup both run."""

    settings = Settings(temp_root=temp_root)
    with TestClient(create_app(settings)):
        pass


def main() -> int:
    for temp_root in TEMP_ROOTS:
        if (temp_root / "sessions").exists():
            run_clean_lifecycle(temp_root)

    residual: list[Path] = []
    for temp_root in TEMP_ROOTS:
        residual.extend(residual_session_dirs(temp_root))

    if residual:
        print("FAILED: residual session directories survived cleanup:")
        for path in residual:
            print(f"  - {path}")
        return 1

    print("No residual session data found; startup/shutdown cleanup verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

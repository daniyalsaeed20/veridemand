"""Cross-platform validation orchestrator.

Runs the full validation suite in a sensible fail-fast order. Each command is
printed before it runs; the first failure stops the run and its exit code is
preserved. Covers Phase 0-4 (backend + frontend tests, build, E2E, LibreOffice
availability, OCR verify when models are present, and a residual-session-data
guard).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = f'"{sys.executable}"'

# (label, shell command) in fail-fast order.
STEPS: list[tuple[str, str]] = [
    ("Lockfile: uv", "uv lock --check"),
    ("Lockfile: pnpm", "pnpm install --frozen-lockfile"),
    ("Legacy-scope check", f"{PYTHON} scripts/check_no_legacy_scope.py"),
    ("Private-corpus tracking guard", f"{PYTHON} scripts/check_no_private_corpus.py"),
    ("Dependency-boundary guard", f"{PYTHON} scripts/check_dependency_boundary.py"),
    ("Contract generation and drift check", f"{PYTHON} scripts/check_contracts.py"),
    ("Backend format check", "uv run ruff format --check backend scripts model_development"),
    ("Backend lint", "uv run ruff check backend scripts model_development"),
    ("Backend type check", "uv run mypy backend scripts"),
    (
        "LibreOffice availability",
        f'{PYTHON} -c "from backend.app.settings.config import Settings; '
        f"from backend.app.canonical.libreoffice import LibreOfficeService; "
        f'r=LibreOfficeService(Settings()).resolve(); print(r.executable, r.version)"',
    ),
    ("Backend tests", "uv run pytest"),
    ("Frontend format check", "pnpm -C frontend format:check"),
    ("Frontend lint", "pnpm -C frontend lint"),
    ("Frontend type check", "pnpm -C frontend typecheck"),
    ("Frontend unit tests", "pnpm -C frontend test"),
    ("PDF.js WASM sync", f"{PYTHON} scripts/verify_pdfjs_wasm.py --sync --clean --http-check"),
    ("Frontend production build", "pnpm -C frontend build"),
    (
        "PDF.js WASM dist check",
        f"{PYTHON} scripts/verify_pdfjs_wasm.py --require-dist --http-check",
    ),
]

OCR_VERIFY_STEP: tuple[str, str] = (
    "OCR model verify",
    "uv run --group ocr python scripts/verify_ocr_runtime.py",
)

OCR_INTEGRATION_STEP: tuple[str, str] = (
    "OCR integration smoke",
    "uv run --group ocr pytest backend/tests/test_ocr_integration.py -v",
)

E2E_STEP: tuple[str, str] = ("End-to-end smoke test", "pnpm -C frontend test:e2e")

RESIDUAL_STEP: tuple[str, str] = (
    "Residual session-data check",
    f"{PYTHON} scripts/check_no_residual_sessions.py",
)


def _ocr_models_present() -> bool:
    record = ROOT / ".models" / "paddleocr" / "model-record.json"
    return record.is_file()


def run_step(label: str, command: str) -> int:
    print(f"\n=== {label} ===")
    print(f"+ {command}")
    result = subprocess.run(command, cwd=ROOT, shell=True, check=False)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Phase 0 validation suite.")
    parser.add_argument(
        "--skip-e2e",
        action="store_true",
        help="Skip the Playwright end-to-end smoke test (run it as a separate job).",
    )
    args = parser.parse_args(argv)

    steps = list(STEPS)
    if _ocr_models_present():
        print("\n=== OCR models detected; including verify + integration ===")
        steps.append(OCR_VERIFY_STEP)
        steps.append(OCR_INTEGRATION_STEP)
    else:
        print(
            "\n=== OCR models absent "
            "(.models/paddleocr/model-record.json); skipping OCR verify/integration ==="
        )
    if not args.skip_e2e:
        steps.append(E2E_STEP)
    # Always verify no runtime session data was left on disk.
    steps.append(RESIDUAL_STEP)

    for label, command in steps:
        code = run_step(label, command)
        if code != 0:
            print(f"\nFAILED: {label} (exit code {code})")
            return code

    print("\nAll validation steps passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

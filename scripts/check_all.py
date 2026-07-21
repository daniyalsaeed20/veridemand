"""Cross-platform Phase 0 validation orchestrator.

Runs the full validation suite in a sensible fail-fast order. Each command is
printed before it runs; the first failure stops the run and its exit code is
preserved.
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
    ("Contract generation and drift check", f"{PYTHON} scripts/check_contracts.py"),
    ("Backend format check", "uv run ruff format --check backend scripts"),
    ("Backend lint", "uv run ruff check backend scripts"),
    ("Backend type check", "uv run mypy backend scripts"),
    ("Backend tests", "uv run pytest"),
    ("Frontend format check", "pnpm -C frontend format:check"),
    ("Frontend lint", "pnpm -C frontend lint"),
    ("Frontend type check", "pnpm -C frontend typecheck"),
    ("Frontend unit tests", "pnpm -C frontend test"),
    ("Frontend production build", "pnpm -C frontend build"),
]

E2E_STEP: tuple[str, str] = ("End-to-end smoke test", "pnpm -C frontend test:e2e")


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
    if not args.skip_e2e:
        steps.append(E2E_STEP)

    for label, command in steps:
        code = run_step(label, command)
        if code != 0:
            print(f"\nFAILED: {label} (exit code {code})")
            return code

    print("\nAll Phase 0 validation steps passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

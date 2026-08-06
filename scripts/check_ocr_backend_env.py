#!/usr/bin/env python3
"""Validate and print OCR-only backend launch identity before uvicorn starts."""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_probe(source: str) -> int:
    """Run a tiny probe in this interpreter without static imports in this file."""
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    env_name = os.environ.get("UV_PROJECT_ENVIRONMENT", "").strip() or ".venv-ocr"
    if env_name != ".venv-ocr":
        print(
            f"ERROR: OCR backend requires UV_PROJECT_ENVIRONMENT=.venv-ocr (got {env_name!r}).",
            file=sys.stderr,
        )
        return 2

    python = Path(sys.executable).resolve()
    if ".venv-ocr" not in str(python).replace("\\", "/"):
        print(
            f"ERROR: sys.executable is not inside .venv-ocr: {python}",
            file=sys.stderr,
        )
        return 2

    # Probes use subprocess so this script stays outside the Phase-4 OCR /
    # Torch import allowlists while still validating the OCR-only environment.
    if _run_probe("import torch") == 0:
        print("ERROR: Torch is present in .venv-ocr; refuse to start OCR backend.", file=sys.stderr)
        return 2

    if _run_probe("import paddle; import paddleocr") != 0:
        print("ERROR: Paddle/PaddleOCR import failed in .venv-ocr.", file=sys.stderr)
        return 2

    commit = "unknown"
    with contextlib.suppress(Exception):
        commit = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            or "unknown"
        )

    print("VeriDemand OCR backend launch")
    print(f"  python: {python}")
    print(f"  UV_PROJECT_ENVIRONMENT: {env_name}")
    print(f"  git_commit: {commit}")
    print("  backend_url: http://127.0.0.1:8000")
    print("  frontend_url: http://localhost:5173")
    print("  torch: absent")
    print("  paddle: present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate and print OCR-only backend launch identity before uvicorn starts."""

from __future__ import annotations

import contextlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _package_present(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _run_probe(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _models_ok() -> bool:
    model_root = ROOT / ".models" / "paddleocr"
    record = model_root / "model-record.json"
    det = model_root / "PP-OCRv5_mobile_det"
    rec = model_root / "PP-OCRv5_mobile_rec"
    if not record.is_file() or not det.is_dir() or not rec.is_dir():
        return False
    return any(det.iterdir()) and any(rec.iterdir())


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
            "ERROR: sys.executable is not inside .venv-ocr "
            "(sanitized env name check failed for executable).",
            file=sys.stderr,
        )
        return 2

    # find_spec only — never import Torch merely to probe presence.
    if _package_present("torch"):
        print("ERROR: Torch is present in .venv-ocr; refuse to start OCR backend.", file=sys.stderr)
        return 2
    if _package_present("torchvision"):
        print(
            "ERROR: Torchvision is present in .venv-ocr; refuse to start OCR backend.",
            file=sys.stderr,
        )
        return 2

    paddle_probe = _run_probe(
        "import paddle; import paddleocr; paddle.utils.run_check(); print('ok')"
    )
    if paddle_probe.returncode != 0:
        print("ERROR: Paddle/PaddleOCR import or paddle.utils.run_check() failed.", file=sys.stderr)
        err = (paddle_probe.stderr or paddle_probe.stdout or "").strip().splitlines()
        if err:
            print(f"  detail: {err[-1][:200]}", file=sys.stderr)
        return 2

    if not _models_ok():
        print(
            "ERROR: OCR model assets missing or incomplete under .models/paddleocr. "
            "Run: pnpm models:ocr:bootstrap && pnpm models:ocr:verify",
            file=sys.stderr,
        )
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
    print("  python_environment: .venv-ocr")
    print(f"  UV_PROJECT_ENVIRONMENT: {env_name}")
    print(f"  git_commit: {commit}")
    print("  backend_url: http://127.0.0.1:8000")
    print("  frontend_url: http://localhost:5173")
    print("  torch: absent")
    print("  torchvision: absent")
    print("  paddle: present")
    print("  paddle_run_check: ok")
    print("  ocr_models: present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

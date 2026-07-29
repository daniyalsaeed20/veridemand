"""Privacy-safe build identity for health/readiness and acceptance gates."""

from __future__ import annotations

import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def resolve_git_commit() -> str | None:
    """Return short git commit SHA when available; never raise or expose paths."""

    env_commit = os.environ.get("VERIDEMAND_GIT_COMMIT") or os.environ.get("GIT_COMMIT")
    if env_commit:
        return env_commit.strip()[:40] or None
    try:
        root = Path(__file__).resolve().parents[2]
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if completed.returncode != 0:
            return None
        sha = (completed.stdout or "").strip()
        return sha[:40] if sha else None
    except (OSError, subprocess.SubprocessError, TimeoutError):
        return None


def worker_generation() -> int:
    """Monotonic worker generation from env (defaults to 1)."""

    raw = os.environ.get("VERIDEMAND_WORKER_GENERATION", "1")
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def configuration_profile(settings: object) -> str:
    """Stable configuration profile label (no secrets or paths)."""

    env_name = getattr(settings, "environment", None) or os.environ.get(
        "VERIDEMAND_ENVIRONMENT", "development"
    )
    ocr_enabled = bool(getattr(settings, "ocr_enabled", True))
    fast_pass = bool(getattr(settings, "ocr_fast_pass_enabled", True))
    parts = [str(env_name), "ocr_on" if ocr_enabled else "ocr_off"]
    if ocr_enabled:
        parts.append("fast_pass" if fast_pass else "single_pass")
    return "+".join(parts)


def build_identity_fields(settings: object) -> dict[str, object]:
    """Fields safe to expose on health endpoints."""

    return {
        "application_version": str(getattr(settings, "app_version", "0.0.0")),
        "git_commit": resolve_git_commit(),
        "process_id": os.getpid(),
        "worker_generation": worker_generation(),
        "configuration_profile": configuration_profile(settings),
        "python_implementation": sys.implementation.name,
    }

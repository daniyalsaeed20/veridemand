"""Git-ignore protection for private remediation outputs."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PRIVATE_PATHS = [
    "tmp/extraction-remediation/",
    "tmp/extraction-forensic-investigation/",
    "docs/example/EG90156.pdf",
]


def is_ignored(rel_path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", rel_path],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def assert_private_paths_ignored(paths: list[str] | None = None) -> list[str]:
    """Return list of paths that are NOT ignored (failures)."""
    failures: list[str] = []
    for p in paths or PRIVATE_PATHS:
        # For directories, check a sentinel child if needed
        check = p
        if p.endswith("/"):
            # git check-ignore works on the directory pattern via tmp/
            check = p.rstrip("/")
        if not is_ignored(check):
            # Also try with trailing content
            if not is_ignored(p) and not is_ignored(f"{check}/README.txt"):
                failures.append(p)
    return failures


def assert_not_tracked(glob_patterns: list[str] | None = None) -> list[str]:
    patterns = glob_patterns or [
        "tmp/extraction-remediation/**",
        "docs/example/*.pdf",
        "docs/example/*.docx",
    ]
    tracked: list[str] = []
    for pattern in patterns:
        result = subprocess.run(
            ["git", "ls-files", pattern],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        tracked.extend([line for line in result.stdout.splitlines() if line.strip()])
    return tracked

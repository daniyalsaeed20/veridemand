"""Fail CI when probable private corpus documents are tracked by Git.

Inspects:
- tracked paths (`git ls-files`)
- recent Phase 4 branch history path names (no file contents)
- common build / test artifact trees when present on disk (path names only)
- documentation paths for private basename tokens

Never opens or logs private file contents or OCR/native transcripts.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_ALLOWED_PRIVATE = frozenset(
    {
        "fixtures/private/.gitkeep",
        "fixtures/private/README.example.md",
        "fixtures/private/visual-ocr-manifest.local.json.example",
        "fixtures/private/throughput-corpus.local.json.example",
        "fixtures/private/phase45-routing.local.json.example",
        "fixtures/private/phase4-final-batch.local.json.example",
    }
)

_DOC_EXT = (".pdf", ".docx", ".doc", ".tif", ".tiff", ".png", ".jpg", ".jpeg", ".webp")

# Basename heuristics for known private regression corpus tokens (no contents).
_PRIVATE_BASENAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^srmc-sj\.pdf$", re.IGNORECASE),
    re.compile(r"^wellstar-sj\.pdf$", re.IGNORECASE),
    re.compile(r"^wellstar-ortho\.pdf$", re.IGNORECASE),
    re.compile(r"^MR\s+\d{4,}\.pdf$", re.IGNORECASE),
    re.compile(r"^MEDICAL\s+RECORDS", re.IGNORECASE),
    re.compile(r"^Final Medical Records", re.IGNORECASE),
    re.compile(r"^Shakur\s+Ali", re.IGNORECASE),
)

_ARTIFACT_ROOTS = (
    "frontend/dist",
    "frontend/playwright-report",
    "frontend/test-results",
    "temp",
    "tmp",
    "temp-e2e",
)


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    raw = result.stdout.decode("utf-8", errors="replace")
    return [path for path in raw.split("\0") if path]


def _history_paths(range_spec: str = "phase-4-visual-detection-printed-ocr-v1..HEAD") -> list[str]:
    """Return path names touched in the Phase 4 tag→HEAD range (opaque paths only)."""

    try:
        result = subprocess.run(
            ["git", "log", "--name-only", "--pretty=format:", range_spec],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30.0,
        )
    except (OSError, subprocess.SubprocessError, TimeoutError):
        return []
    if result.returncode != 0:
        # Tag may be missing on shallow clones — fall back to recent commits.
        try:
            result = subprocess.run(
                ["git", "log", "--name-only", "--pretty=format:", "-n", "200"],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=30.0,
            )
        except (OSError, subprocess.SubprocessError, TimeoutError):
            return []
        if result.returncode != 0:
            return []
    paths: list[str] = []
    for line in (result.stdout or "").splitlines():
        path = line.strip().replace("\\", "/")
        if path:
            paths.append(path)
    return paths


def _artifact_paths() -> list[str]:
    found: list[str] = []
    for rel in _ARTIFACT_ROOTS:
        root = ROOT / rel
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                found.append(path.relative_to(ROOT).as_posix())
    return found


def _is_document(path: str) -> bool:
    lower = path.lower()
    return any(lower.endswith(ext) for ext in _DOC_EXT)


def _basename_violation(path: str) -> str | None:
    normalised = path.replace("\\", "/")
    name = Path(normalised).name
    if normalised.startswith("fixtures/private/"):
        return None
    if any(pattern.search(name) for pattern in _PRIVATE_BASENAME_PATTERNS):
        return f"probable private corpus basename outside fixtures/private/: {normalised}"
    return None


def _violations(tracked: list[str]) -> list[str]:
    found: list[str] = []
    for path in tracked:
        normalised = path.replace("\\", "/")
        name = Path(normalised).name

        if normalised.startswith("docs/example/") and _is_document(normalised):
            found.append(f"tracked document under docs/example/: {normalised}")
            continue

        if normalised.startswith("fixtures/private/"):
            if normalised not in _ALLOWED_PRIVATE:
                found.append(f"tracked file under fixtures/private/: {normalised}")
            continue

        banned = _basename_violation(normalised)
        if banned:
            found.append(banned)
            continue

        if normalised.startswith("docs/") and any(
            pattern.search(name) for pattern in _PRIVATE_BASENAME_PATTERNS
        ):
            found.append(f"private basename token under docs/: {normalised}")
    return found


def _extra_surface_violations() -> list[str]:
    found: list[str] = []
    for path in _history_paths():
        banned = _basename_violation(path)
        if banned:
            found.append(f"history:{banned}")
    for path in _artifact_paths():
        banned = _basename_violation(path)
        if banned:
            found.append(f"artifact:{banned}")
        normalised = path.replace("\\", "/")
        if normalised.startswith("frontend/public/") and _is_document(normalised):
            found.append(f"artifact:document under frontend/public/: {normalised}")
    return found


def main() -> int:
    tracked = _tracked_files()
    problems = _violations(tracked)
    problems.extend(_extra_surface_violations())
    # De-duplicate while preserving order.
    deduped: list[str] = []
    seen: set[str] = set()
    for item in problems:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    if deduped:
        print("Private-corpus tracking guard FAILED:")
        for item in deduped:
            print(f"  - {item}")
        print(
            "\nPrivate medical/case binaries must remain gitignored under "
            "fixtures/private/ only. Remove them from the index before committing."
        )
        return 1
    print(
        "Private-corpus tracking guard passed "
        f"({len(tracked)} tracked paths + history/artifact surfaces inspected; "
        "no contents read)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

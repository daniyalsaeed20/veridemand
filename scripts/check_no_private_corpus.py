"""Fail CI when probable private corpus documents are tracked by Git.

Inspects *tracked paths only* (`git ls-files`). Never opens or logs file
contents. Private medical/case binaries belong solely under the gitignored
`fixtures/private/` tree (except the committed `.gitkeep` / README.example.md).
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


def _is_document(path: str) -> bool:
    lower = path.lower()
    return any(lower.endswith(ext) for ext in _DOC_EXT)


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

        if any(
            pattern.search(name) for pattern in _PRIVATE_BASENAME_PATTERNS
        ) and not normalised.startswith("fixtures/private/"):
            found.append(
                f"probable private corpus basename tracked outside fixtures/private/: {normalised}"
            )
    return found


def main() -> int:
    tracked = _tracked_files()
    problems = _violations(tracked)
    if problems:
        print("Private-corpus tracking guard FAILED:")
        for item in problems:
            print(f"  - {item}")
        print(
            "\nPrivate medical/case binaries must remain gitignored under "
            "fixtures/private/ only. Remove them from the index before committing."
        )
        return 1
    print(
        "Private-corpus tracking guard passed "
        f"({len(tracked)} tracked paths inspected; no contents read)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

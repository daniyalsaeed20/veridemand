"""Fail if removed demand-letter (legacy) scope reappears in active code.

Scans executable code under ``backend/``, ``frontend/src/`` and ``scripts/``
for known legacy module names and concepts. The canonical specification and the
Phase 0 removal report are allowed to describe the excluded functionality, so
documentation is not scanned and this checker excludes itself.

Patterns are deliberately specific to avoid rejecting legitimate generic
document-extraction vocabulary.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = (ROOT / "backend", ROOT / "frontend" / "src", ROOT / "scripts")
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
EXCLUDED_DIR_PARTS = {"node_modules", "__pycache__", ".venv", "dist", ".mypy_cache"}
EXCLUDED_FILES = {(ROOT / "scripts" / "check_no_legacy_scope.py").resolve()}

LEGACY_PATTERNS: tuple[str, ...] = (
    r"demand[_\- ]?letter",
    r"DemandLetter",
    r"legal[_\- ]?workflow",
    r"legal[_\- ]?analysis",
    r"legal[_\- ]?review",
    r"chronology",
    r"contradiction",
    r"settlement",
    r"claim[_\- ]?valuation",
    r"draft[_\- ]?generation",
    r"demand[_\- ]?generation",
    r"docx[_\- ]?generat",
    r"case[_\- ]?facts",
    r"medical[_\- ]?analysis",
    r"letter[_\- ]?template",
)


def _iter_code_files() -> Iterator[Path]:
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in CODE_SUFFIXES:
                continue
            if any(part in EXCLUDED_DIR_PARTS for part in path.parts):
                continue
            if path.resolve() in EXCLUDED_FILES:
                continue
            yield path


def main() -> int:
    compiled = [(p, re.compile(p, re.IGNORECASE)) for p in LEGACY_PATTERNS]
    hits: list[str] = []

    for path in _iter_code_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for pattern, regex in compiled:
                if regex.search(line):
                    rel = path.relative_to(ROOT).as_posix()
                    hits.append(f"{rel}:{line_number} matched /{pattern}/ -> {line.strip()[:120]}")

    if hits:
        print("Legacy demand-letter scope found in active code:")
        for hit in hits:
            print(f"  {hit}")
        print(f"\nFound {len(hits)} legacy-scope reference(s).")
        return 1

    print("OK: no legacy demand-letter scope found in active code.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

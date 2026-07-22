#!/usr/bin/env python3
"""Fail if Phase-4+ extraction dependencies appear as direct imports or deps.

pdfplumber transitively depends on pypdfium2; that is allowed as an unused
transitive package. Application code must not import pypdfium2, paddleocr,
onnxruntime, openai, tesseract, or opencv, and those packages must not be
declared as direct project dependencies.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_IMPORTS = (
    "pypdfium2",
    "paddleocr",
    "paddle",
    "onnxruntime",
    "openai",
    "cv2",
    "pytesseract",
    "tesseract",
)
FORBIDDEN_DIRECT = (
    "pypdfium2",
    "paddleocr",
    "paddlepaddle",
    "onnxruntime",
    "openai",
    "opencv-python",
    "pytesseract",
)

_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+(" + "|".join(re.escape(n) for n in FORBIDDEN_IMPORTS) + r")\b",
    re.MULTILINE,
)


def main() -> int:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # Only the project.dependencies block.
    dep_block = re.search(r"dependencies\s*=\s*\[(.*?)\]", pyproject, re.DOTALL)
    if dep_block:
        block = dep_block.group(1).lower()
        for name in FORBIDDEN_DIRECT:
            if name.lower() in block:
                print(f"Forbidden direct dependency declared: {name}")
                return 1

    failures: list[str] = []
    for path in (ROOT / "backend").rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if _IMPORT_RE.search(text):
            failures.append(str(path.relative_to(ROOT)))
        # Also forbid rendering APIs that would decode page images.
        if "page.to_image(" in text or ".to_image(" in text:
            failures.append(f"{path.relative_to(ROOT)} (to_image call)")

    if failures:
        print("Forbidden Phase-4+ imports or render calls found:")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("Dependency boundary guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

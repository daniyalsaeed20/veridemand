#!/usr/bin/env python3
"""Fail if Phase-5+ extraction dependencies appear as direct imports or deps.

Phase 4 allows intentional ``pypdfium2`` / ``paddleocr`` / ``paddle`` /
``numpy`` / ``psutil`` imports under ``backend/app/extraction/visual/`` and
related bootstrap/verify scripts. Handwriting (onnxruntime), vision LLM
(openai), and OCR-unrelated OpenCV remain forbidden in application code.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Still forbidden everywhere in application code (Phase 5+).
FORBIDDEN_IMPORTS = (
    "onnxruntime",
    "openai",
    "cv2",
    "pytesseract",
    "tesseract",
)

# Phase-4 OCR stack is allowed only in these path prefixes (posix-style).
PHASE4_ALLOWED_PREFIXES = (
    "backend/app/extraction/visual/",
    "backend/app/health/service.py",
    "scripts/bootstrap_ocr_models.py",
    "scripts/verify_ocr_runtime.py",
    "scripts/diagnose_mkldnn_windows.py",
    "scripts/verify_windows_dev_runtime.py",
    "scripts/evaluate_printed_ocr.py",
    "scripts/evaluate_private_visual_ocr.py",
    "scripts/generate_veridemand_regression_pdf.py",
)

# Phase-4 packages may appear in the ocr dependency group, and pypdfium2 may be
# a direct project dependency. These remain forbidden as direct *core* deps
# except pypdfium2.
FORBIDDEN_CORE_DIRECT = (
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

_OCR_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+(pypdfium2|paddleocr|paddle|numpy|psutil)\b",
    re.MULTILINE,
)


def _is_phase4_allowed(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    for prefix in PHASE4_ALLOWED_PREFIXES:
        if rel == prefix.rstrip("/") or rel.startswith(prefix):
            return True
    return False


def _core_dependency_block(pyproject: str) -> str:
    match = re.search(r"(?m)^dependencies\s*=\s*\[(.*?)\]", pyproject, re.DOTALL)
    return match.group(1).lower() if match else ""


def main() -> int:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    core_block = _core_dependency_block(pyproject)
    for name in FORBIDDEN_CORE_DIRECT:
        if name.lower() in core_block:
            print(f"Forbidden direct core dependency declared: {name}")
            return 1

    failures: list[str] = []
    for path in (ROOT / "backend").rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(ROOT))
        if _IMPORT_RE.search(text):
            failures.append(rel)
        if _OCR_IMPORT_RE.search(text) and not _is_phase4_allowed(path):
            failures.append(f"{rel} (Phase-4 OCR import outside visual/)")
        if ("page.to_image(" in text or ".to_image(" in text) and not _is_phase4_allowed(path):
            failures.append(f"{rel} (to_image call)")

    # Bootstrap/verify scripts may import OCR stack; other scripts must not.
    for path in (ROOT / "scripts").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(ROOT))
        if _IMPORT_RE.search(text):
            failures.append(rel)
        if _OCR_IMPORT_RE.search(text) and not _is_phase4_allowed(path):
            failures.append(f"{rel} (Phase-4 OCR import outside allowed scripts)")

    if failures:
        print("Forbidden Phase-5+ imports or misplaced Phase-4 imports found:")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("Dependency boundary guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Fail if Phase-5+ extraction dependencies appear outside approved prefixes.

Phase 4 allows intentional ``pypdfium2`` / ``paddleocr`` / ``paddle`` /
``numpy`` / ``psutil`` imports under ``backend/app/extraction/visual/`` and
related bootstrap/verify scripts.

Phase 5 allows ``onnxruntime`` only under ``handwriting_router`` and approved
verify scripts. The ``onnx`` package is tooling-only (model-dev / tests /
verify scripts), not general application services.

Vision LLM (openai), OpenCV (cv2), and HTR engines remain forbidden.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Forbidden everywhere except explicitly allowlisted prefixes below.
FORBIDDEN_IMPORTS = (
    "onnxruntime",
    "onnx",
    "openai",
    "cv2",
    "pytesseract",
    "tesseract",
    "transformers",
    "trocr",
    "kraken",
    "pylaia",
)

# onnxruntime may be imported only here.
ONNXRUNTIME_ALLOWED_PREFIXES = (
    "backend/app/extraction/handwriting_router/",
    "scripts/verify_handwriting_classifier.py",
)

# onnx (structural tooling) may be imported only here — not general app services.
ONNX_TOOLING_ALLOWED_PREFIXES = (
    "backend/app/extraction/handwriting_router/",
    "scripts/verify_handwriting_classifier.py",
    "scripts/generate_handwriting_classifier_fixture.py",
    "backend/tests/",
)

# Phase-4 OCR stack is allowed only in these path prefixes (posix-style).
PHASE4_ALLOWED_PREFIXES = (
    "backend/app/extraction/visual/",
    "backend/app/extraction/routing/",
    "backend/app/health/service.py",
    "scripts/bootstrap_ocr_models.py",
    "scripts/verify_ocr_runtime.py",
    "scripts/diagnose_mkldnn_windows.py",
    "scripts/diagnose_phase42_stall.py",
    "scripts/verify_windows_dev_runtime.py",
    "scripts/evaluate_printed_ocr.py",
    "scripts/evaluate_private_visual_ocr.py",
    "scripts/generate_veridemand_regression_pdf.py",
    "scripts/benchmark_phase43_ocr.py",
    "scripts/accept_phase43_multipage_progress.py",
    "scripts/generate_phase43_ocr_fixtures.py",
    "scripts/diagnose_phase43_render_dims.py",
    "scripts/phase5/populate_private_evidence.py",
)

# Phase-4 packages may appear in the ocr dependency group, and pypdfium2 may be
# a direct project dependency. onnxruntime is an approved Phase 5 core dep.
# These remain forbidden as direct *core* deps.
FORBIDDEN_CORE_DIRECT = (
    "paddleocr",
    "paddlepaddle",
    "openai",
    "opencv-python",
    "pytesseract",
    "onnxruntime-gpu",
)

_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+(" + "|".join(re.escape(n) for n in FORBIDDEN_IMPORTS) + r")\b",
    re.MULTILINE,
)

_OCR_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+(pypdfium2|paddleocr|paddle|numpy|psutil)\b",
    re.MULTILINE,
)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _is_under(path: Path, prefixes: tuple[str, ...]) -> bool:
    rel = _rel(path)
    return any(rel == prefix.rstrip("/") or rel.startswith(prefix) for prefix in prefixes)


def _is_phase4_allowed(path: Path) -> bool:
    return _is_under(path, PHASE4_ALLOWED_PREFIXES)


def _core_dependency_block(pyproject: str) -> str:
    match = re.search(r"(?m)^dependencies\s*=\s*\[(.*?)\]", pyproject, re.DOTALL)
    return match.group(1).lower() if match else ""


def _import_allowed(path: Path, package: str) -> bool:
    if package == "onnxruntime":
        return _is_under(path, ONNXRUNTIME_ALLOWED_PREFIXES)
    if package == "onnx":
        return _is_under(path, ONNX_TOOLING_ALLOWED_PREFIXES)
    # openai, cv2, HTR — never allowed in app/scripts (tests may mention names
    # only as strings; this guard scans import statements).
    return False


def main() -> int:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    core_block = _core_dependency_block(pyproject)
    for name in FORBIDDEN_CORE_DIRECT:
        if name.lower() in core_block:
            print(f"Forbidden direct core dependency declared: {name}")
            return 1

    failures: list[str] = []
    scan_roots = [ROOT / "backend", ROOT / "scripts"]
    skip_self = ROOT / "scripts" / "check_dependency_boundary.py"
    numpy_ok_prefixes = (
        "backend/app/extraction/handwriting_router/",
        "backend/app/datasets/phase5/",
        "scripts/generate_handwriting_classifier_fixture.py",
        "scripts/verify_handwriting_classifier.py",
        "scripts/phase5/",
        "scripts/phase5_dataset_cli.py",
    )
    for root in scan_roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if path.resolve() == skip_self.resolve():
                continue
            text = path.read_text(encoding="utf-8")
            rel = _rel(path)
            for match in _IMPORT_RE.finditer(text):
                package = match.group(1)
                if not _import_allowed(path, package):
                    failures.append(f"{rel} (forbidden import: {package})")
            if "tests" in path.parts:
                continue
            ocr_hits = _OCR_IMPORT_RE.findall(text)
            if ocr_hits and not _is_phase4_allowed(path):
                banned = [h for h in ocr_hits if h in ("paddleocr", "paddle", "pypdfium2")]
                numpy_only = all(h in ("numpy", "psutil") for h in ocr_hits)
                if banned:
                    failures.append(f"{rel} (Phase-4 OCR import outside visual/)")
                elif not numpy_only or not _is_under(path, numpy_ok_prefixes):
                    if not numpy_only:
                        failures.append(f"{rel} (Phase-4 OCR import outside visual/)")
                    elif not _is_under(path, numpy_ok_prefixes):
                        failures.append(f"{rel} (numpy/psutil import outside allowed paths)")
            if "page.to_image(" in text and not _is_phase4_allowed(path):
                failures.append(f"{rel} (to_image call)")

    if failures:
        print("Forbidden Phase-5+ imports or misplaced Phase-4 imports found:")
        for item in sorted(set(failures)):
            print(f"  - {item}")
        return 1
    print("Dependency boundary guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

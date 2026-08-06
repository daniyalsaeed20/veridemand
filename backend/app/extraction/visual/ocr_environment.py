"""Detect OCR Python environment without importing Torch."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

from backend.app.contracts.ocr_runtime import OcrPythonEnvironmentKind


@dataclass(frozen=True)
class OcrEnvironmentDiagnostics:
    """Privacy-safe OCR process environment snapshot."""

    kind: OcrPythonEnvironmentKind
    executable_environment: str | None
    torch_present: bool
    torchvision_present: bool
    paddle_present: bool
    environment_conflict: bool


def _package_present(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def sanitized_executable_environment(executable: str | None = None) -> str | None:
    """Return only the virtualenv directory basename (for example ``.venv-ocr``)."""

    raw = executable or sys.executable
    try:
        parts = Path(raw).resolve().parts
    except OSError:
        parts = Path(raw).parts
    for name in (".venv-ocr", ".venv-model-dev", ".venv"):
        if name in parts:
            return name
    # Scripts/bin parent often is the venv root name.
    try:
        parent = Path(raw).resolve().parent.parent.name
    except OSError:
        parent = Path(raw).parent.parent.name
    if parent.startswith(".venv"):
        return parent
    return None


def classify_python_environment_kind(
    *,
    executable: str | None = None,
    torch_present: bool | None = None,
    torchvision_present: bool | None = None,
    paddle_present: bool | None = None,
) -> OcrPythonEnvironmentKind:
    """Classify the process environment using path tokens and package discovery."""

    env_name = sanitized_executable_environment(executable)
    torch_p = _package_present("torch") if torch_present is None else torch_present
    vision_p = (
        _package_present("torchvision") if torchvision_present is None else torchvision_present
    )
    paddle_p = _package_present("paddle") if paddle_present is None else paddle_present

    if env_name == ".venv-ocr":
        if torch_p or vision_p:
            return OcrPythonEnvironmentKind.MIXED
        return OcrPythonEnvironmentKind.OCR
    if env_name == ".venv-model-dev":
        return OcrPythonEnvironmentKind.MODEL_DEV
    if env_name == ".venv":
        if (torch_p or vision_p) and paddle_p:
            return OcrPythonEnvironmentKind.MIXED
        return OcrPythonEnvironmentKind.DEFAULT
    if env_name is None:
        if (torch_p or vision_p) and paddle_p:
            return OcrPythonEnvironmentKind.MIXED
        return OcrPythonEnvironmentKind.SYSTEM
    if (torch_p or vision_p) and paddle_p:
        return OcrPythonEnvironmentKind.MIXED
    return OcrPythonEnvironmentKind.UNKNOWN


def probe_ocr_environment(executable: str | None = None) -> OcrEnvironmentDiagnostics:
    """Probe packages with find_spec only — never import Torch to test presence."""

    torch_p = _package_present("torch")
    vision_p = _package_present("torchvision")
    paddle_p = _package_present("paddle")
    kind = classify_python_environment_kind(
        executable=executable,
        torch_present=torch_p,
        torchvision_present=vision_p,
        paddle_present=paddle_p,
    )
    conflict = bool((torch_p or vision_p) and paddle_p) or kind in {
        OcrPythonEnvironmentKind.MIXED,
        OcrPythonEnvironmentKind.MODEL_DEV,
        OcrPythonEnvironmentKind.DEFAULT,
    }
    if kind is OcrPythonEnvironmentKind.OCR and not torch_p and not vision_p:
        conflict = False
    elif kind is OcrPythonEnvironmentKind.SYSTEM and not paddle_p:
        conflict = bool((torch_p or vision_p) and paddle_p)
    return OcrEnvironmentDiagnostics(
        kind=kind,
        executable_environment=sanitized_executable_environment(executable),
        torch_present=torch_p,
        torchvision_present=vision_p,
        paddle_present=paddle_p,
        environment_conflict=conflict,
    )


def dll_failure_requires_restart(
    diagnostics: OcrEnvironmentDiagnostics,
    *,
    technical_detail: str | None = None,
) -> bool:
    """True when a DLL/native load failure cannot be fixed inside this process."""

    if diagnostics.environment_conflict:
        return True
    if diagnostics.kind is not OcrPythonEnvironmentKind.OCR:
        return True
    if diagnostics.torch_present or diagnostics.torchvision_present:
        return True
    lowered = (technical_detail or "").lower()
    return "torch" in lowered and ("dll" in lowered or "shm" in lowered or "load" in lowered)

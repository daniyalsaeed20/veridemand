"""Safe zip extraction for Handwritten ASAP archives."""

from __future__ import annotations

import zipfile
from pathlib import Path


class UnsafeArchiveError(ValueError):
    """Path traversal or absolute paths inside zip."""


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_extract_zip(archive: Path, dest: Path) -> dict[str, int]:
    """Extract zip members into dest with path-traversal protection."""

    dest.mkdir(parents=True, exist_ok=True)
    extracted = 0
    skipped = 0
    with zipfile.ZipFile(archive, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if not name or name.endswith("/"):
                continue
            if name.startswith("/") or name.startswith("../") or "/../" in f"/{name}/":
                raise UnsafeArchiveError(f"unsafe zip member path: {name!r}")
            target = (dest / name).resolve()
            if not _is_within(dest, target):
                raise UnsafeArchiveError(f"zip member escapes destination: {name!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, target.open("wb") as out:
                out.write(src.read())
            extracted += 1
    return {"extracted": extracted, "skipped": skipped}

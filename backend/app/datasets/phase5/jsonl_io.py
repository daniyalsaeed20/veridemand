"""JSONL helpers for Phase 5 manifests (atomic append + resume)."""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

from pydantic import BaseModel


def read_jsonl[T: BaseModel](path: Path, model: type[T]) -> list[T]:
    if not path.is_file():
        return []
    rows: list[T] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(model.model_validate_json(text))
            except Exception as exc:
                raise ValueError(f"{path}:{line_no}: {exc}") from exc
    return rows


def iter_jsonl[T: BaseModel](path: Path, model: type[T]) -> Iterator[T]:
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                yield model.model_validate_json(text)
            except Exception as exc:
                raise ValueError(f"{path}:{line_no}: {exc}") from exc


def append_jsonl(path: Path, records: Iterable[BaseModel]) -> int:
    """Append records (O_APPEND + fsync)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(rec.model_dump_json() + "\n" for rec in records)
    if not payload:
        return 0
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return payload.count("\n")


def write_jsonl_atomic(path: Path, records: Iterable[BaseModel]) -> int:
    """Replace a JSONL file atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [rec.model_dump_json() for rec in records]
    raw = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
    return len(lines)


def index_by[T](records: Iterable[T], key: Callable[[T], str]) -> dict[str, T]:
    out: dict[str, T] = {}
    for rec in records:
        out[key(rec)] = rec
    return out

"""NDJSON protocol helpers for the long-lived visual OCR worker.

Stdout carries privacy-safe progress only — never OCR text, never image bytes.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Final

# Keys that must never appear on the progress channel.
_FORBIDDEN_PROGRESS_KEYS: Final[frozenset[str]] = frozenset(
    {
        "text",
        "normalised_text",
        "words",
        "lines",
        "blocks",
        "characters",
        "rec_texts",
        "provisional_native_text",
        "image",
        "bitmap",
        "pixels",
    }
)


def strip_sensitive_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy without forbidden OCR/text keys."""

    return {k: v for k, v in payload.items() if k not in _FORBIDDEN_PROGRESS_KEYS}


def emit_message(payload: dict[str, Any]) -> None:
    """Write one NDJSON progress/control line to stdout."""

    safe = strip_sensitive_fields(payload)
    sys.stdout.write(json.dumps(safe, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def parse_message(line: str | bytes) -> dict[str, Any] | None:
    """Parse one NDJSON line; return None on malformed input."""

    if isinstance(line, bytes):
        text = line.decode("utf-8", errors="replace").strip()
    else:
        text = line.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def encode_message(payload: dict[str, Any]) -> bytes:
    """Encode a control message for worker stdin."""

    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")

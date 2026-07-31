"""Geometry-only page-result helpers (strip OCR text for dataset artefacts)."""

from __future__ import annotations

from typing import Any

_TEXT_KEYS = frozenset(
    {
        "text",
        "normalised_text",
        "ocr_text",
        "transcript",
        "rec_text",
        "rec_texts",
        "filename",
        "source_label",
    }
)


def strip_text_fields(obj: Any) -> Any:
    """Recursively drop text-bearing keys from page-result JSON."""

    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if key in _TEXT_KEYS:
                continue
            out[key] = strip_text_fields(value)
        return out
    if isinstance(obj, list):
        return [strip_text_fields(item) for item in obj]
    return obj


def geometry_only_region(
    bbox: dict[str, float], polygon: dict[str, Any] | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {"bbox": bbox}
    if polygon is not None:
        out["polygon"] = polygon
    return out

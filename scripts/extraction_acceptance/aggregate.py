"""Aggregation and safe-report redaction."""

from __future__ import annotations

import re
from typing import Any

# Patterns that must never appear in committed/safe summaries.
_REDACT_KEYS = frozenset(
    {
        "expected",
        "hypothesized",
        "transcript",
        "expected_transcript",
        "reconstructed_text",
        "text",
        "raw_text",
        "file_hash",
        "sha256",
        "private_path",
        "source_path",
        "absolute_path",
        "reviewer_notes",
        "notes",
        "excerpt",
        "value",
    }
)

_HASH_RE = re.compile(r"\b[a-fA-F0-9]{32,64}\b")
_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"']+|/(?:Users|home|Applications)/[^\s\"']+")


def redact_value(key: str, value: Any) -> Any:
    lk = key.lower()
    if lk in _REDACT_KEYS or any(k in lk for k in ("hash", "path", "transcript", "excerpt")):
        if isinstance(value, str):
            return "[REDACTED]"
        if isinstance(value, list):
            return ["[REDACTED]"] if value else []
        if isinstance(value, dict):
            return {"redacted": True}
        return None
    if isinstance(value, str):
        if _HASH_RE.search(value) or _PATH_RE.search(value):
            return "[REDACTED]"
    return value


def redact_structure(obj: Any, *, parent_key: str = "") -> Any:
    if isinstance(obj, dict):
        return {k: redact_structure(redact_value(k, v), parent_key=k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_structure(v, parent_key=parent_key) for v in obj]
    if parent_key:
        return redact_value(parent_key, obj)
    if isinstance(obj, str) and (_HASH_RE.search(obj) or _PATH_RE.search(obj)):
        return "[REDACTED]"
    return obj


def aggregate_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        k = str(row.get(key) or "unknown")
        buckets.setdefault(k, []).append(row)
    out: dict[str, dict[str, Any]] = {}
    for k, items in buckets.items():
        wers = [float(i["wer"]) for i in items if isinstance(i.get("wer"), (int, float))]
        out[k] = {
            "count": len(items),
            "mean_wer": (sum(wers) / len(wers)) if wers else None,
            "layer_correct": sum(1 for i in items if i.get("layer_correct")),
        }
    return out


def safe_summary(
    *,
    synthetic_fixture_count: int,
    private_document_count: int,
    selected_page_count: int,
    document_classes: list[str],
    annotation_status_counts: dict[str, int],
    baseline_status: str,
    missing_documents: list[str],
    metrics_implemented: list[str],
    test_totals: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "synthetic_fixture_count": synthetic_fixture_count,
        "private_document_count": private_document_count,
        "selected_page_count": selected_page_count,
        "document_classes": sorted(document_classes),
        "annotation_status_counts": annotation_status_counts,
        "baseline_status": baseline_status,
        "missing_documents": missing_documents,
        "metrics_implemented": metrics_implemented,
        "test_totals": test_totals or {},
    }

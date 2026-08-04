"""Privacy-safe aggregate report helpers (no private IDs/paths/text)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def strip_private_fields(obj: Any) -> Any:
    """Recursively drop keys that may contain private identifiers or paths."""

    banned = {
        "crop_id",
        "path",
        "crop_path_private",
        "source_group_id",
        "held_out_source_group",
        "reviewer_id",
        "page_id",
        "document_id",
        "filename",
        "text",
        "transcription",
    }
    if isinstance(obj, dict):
        return {
            k: strip_private_fields(v)
            for k, v in obj.items()
            if k not in banned and not str(k).endswith("_path")
        }
    if isinstance(obj, list):
        return [strip_private_fields(x) for x in obj]
    return obj


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = strip_private_fields(payload)
    path.write_text(json.dumps(safe, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def oof_without_ids(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep numeric diagnostics only for private artefact dumps."""

    out = []
    for p in predictions:
        out.append(
            {
                "label": p.get("label"),
                "logits": p.get("logits"),
                "probabilities": p.get("probabilities"),
                "top_class": p.get("top_class"),
                "top_two_margin": p.get("top_two_margin"),
                "held_out_fold_index": p.get("held_out_fold_index"),
                "config_name": p.get("config_name"),
                "width": p.get("width"),
                "height": p.get("height"),
                "source_category": p.get("source_category"),
                "synthetic": p.get("synthetic", False),
            }
        )
    return out

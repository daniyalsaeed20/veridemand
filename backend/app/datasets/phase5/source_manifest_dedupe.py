"""Deduplicate source-manifest.jsonl by page_id (keep first occurrence)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.datasets.phase5.backup import backup_manifests
from backend.app.datasets.phase5.constants import SOURCE_MANIFEST_DEDUPE_VERSION
from backend.app.datasets.phase5.jsonl_io import read_jsonl, write_jsonl_atomic
from backend.app.datasets.phase5.paths import ensure_layout, manifest_path, reports_dir
from backend.app.datasets.phase5.schemas import SourceRecord


def dedupe_source_manifest(private_root: Path, *, backup: bool = True) -> dict[str, Any]:
    """Rewrite source-manifest to one row per page_id; optional backup first."""

    ensure_layout(private_root)
    path = manifest_path(private_root, "source-manifest.jsonl")
    rows = read_jsonl(path, SourceRecord)
    before = len(rows)
    seen: set[str] = set()
    unique: list[SourceRecord] = []
    for row in rows:
        if row.page_id in seen:
            continue
        seen.add(row.page_id)
        unique.append(row)
    after = len(unique)
    removed = before - after
    backup_name: str | None = None
    if backup and removed > 0:
        dest = backup_manifests(private_root)
        backup_name = dest.name
    if removed > 0:
        write_jsonl_atomic(path, unique)
    meta = {
        "migration_version": SOURCE_MANIFEST_DEDUPE_VERSION,
        "migrated_at": datetime.now(UTC).isoformat(),
        "rows_before": before,
        "rows_after": after,
        "duplicate_rows_removed": removed,
        "unique_page_ids": after,
        "backup_name": backup_name,
    }
    reports = reports_dir(private_root)
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "source-manifest-dedupe.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    return meta

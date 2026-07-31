"""Private dataset backup helpers (gitignored; no external upload)."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from backend.app.datasets.phase5.hashes import sha256_file
from backend.app.datasets.phase5.paths import ensure_layout


def backup_manifests(private_root: Path) -> Path:
    """Copy manifests into a timestamped backup directory; record hashes."""

    ensure_layout(private_root)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = private_root / "backups" / f"backup_{stamp}"
    dest.mkdir(parents=True, exist_ok=False)
    manifests_src = private_root / "manifests"
    manifests_dst = dest / "manifests"
    manifests_dst.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    if manifests_src.is_dir():
        for path in sorted(manifests_src.iterdir()):
            if not path.is_file():
                continue
            target = manifests_dst / path.name
            shutil.copy2(path, target)
            hashes[path.name] = sha256_file(path)
    meta = {
        "created_at": datetime.now(UTC).isoformat(),
        "manifest_sha256": hashes,
        "note": "Private backup; do not commit or upload.",
    }
    (dest / "backup-meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return dest

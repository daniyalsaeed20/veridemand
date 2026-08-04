"""Build train-only ExampleRef lists from prepared ASAP subset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from model_development.handwriting_classifier.public_data import PUBLIC_SOURCE_GROUP_PREFIX
from model_development.handwriting_classifier.train import ExampleRef

AsapVariant = Literal["light", "medium"]


def default_asap_data_root(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[3]
    return root / "model_development" / ".data" / "handwritten_asap"


def load_subset_manifest(
    data_root: Path | None = None,
    *,
    variant: AsapVariant = "medium",
) -> dict[str, Any]:
    root = data_root or default_asap_data_root()
    prepared = root / "prepared"
    name = "subset-manifest-light.json" if variant == "light" else "subset-manifest.json"
    path = prepared / name
    if not path.is_file():
        raise FileNotFoundError(f"ASAP subset manifest missing: {path}. Run prepare-asap first.")
    return json.loads(path.read_text(encoding="utf-8"))


def load_asap_handwriting_refs(
    data_root: Path | None = None,
    *,
    variant: AsapVariant = "medium",
) -> list[ExampleRef]:
    """Public handwriting refs for training only (never project OOF)."""

    root = data_root or default_asap_data_root()
    prepared = root / "prepared"
    manifest = load_subset_manifest(root, variant=variant)
    refs: list[ExampleRef] = []
    for row in manifest.get("selected") or []:
        rel = str(row["prepared_relpath"])
        path = prepared / rel
        if not path.is_file():
            continue
        group = str(row.get("prompt_group_id") or f"{PUBLIC_SOURCE_GROUP_PREFIX}unknown")
        refs.append(
            ExampleRef(
                path=str(path),
                label="handwritten",
                source_group_id=group,
                synthetic=False,
                crop_id=str(row.get("crop_id") or ""),
                public=True,
                project_handwriting=False,
            )
        )
    return refs


def asap_provenance_summary(data_root: Path | None = None) -> dict[str, Any]:
    root = data_root or default_asap_data_root()
    prov_path = root / "provenance" / "licence-record.json"
    if not prov_path.is_file():
        return {}
    return json.loads(prov_path.read_text(encoding="utf-8"))

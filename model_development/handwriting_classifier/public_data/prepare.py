"""Orchestrate Handwritten ASAP prepare: licence → download → extract → subset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from model_development.handwriting_classifier.public_data import (
    ASAP_CROP_TRANSFORM_VERSION,
    ASAP_SUBSET_VERSION,
)
from model_development.handwriting_classifier.public_data.download import (
    LicenceBlockedError,
    ensure_verified_archive,
)
from model_development.handwriting_classifier.public_data.extract import safe_extract_zip
from model_development.handwriting_classifier.public_data.licence import (
    ARCHIVE_FILENAME,
    ATTRIBUTION_TEXT,
    DATASET_CREATORS,
    DATASET_TITLE,
    DATASET_VERSION,
    LICENCE_ID,
    LICENCE_NAME,
    LICENCE_URL,
    OFFICIAL_MD5,
    ZENODO_DOI,
    ZENODO_RECORD_ID,
    ZENODO_RECORD_URL,
    AsapLicenceRecord,
    default_modification_notice,
    today_access_date,
)
from model_development.handwriting_classifier.public_data.refs import default_asap_data_root
from model_development.handwriting_classifier.public_data.sample import build_subset

# asap_light uses first 150 after deterministic shuffle
ASAP_LIGHT_CAP = 150


def prepare_asap(
    data_root: Path | None = None,
    *,
    verify_only: bool = False,
    force_download: bool = False,
    seed: int = 42,
) -> dict[str, Any]:
    """Prepare gitignored ASAP cache. Raises LicenceBlockedError on licence failure."""

    root = data_root or default_asap_data_root()
    root.mkdir(parents=True, exist_ok=True)
    access_date = today_access_date()

    try:
        archive_info = ensure_verified_archive(
            root, verify_only=verify_only, force_download=force_download
        )
    except Exception as exc:
        if "BLOCKED BY LICENSING" in str(exc) or isinstance(exc, LicenceBlockedError):
            raise LicenceBlockedError(str(exc)) from exc
        raise

    if verify_only:
        return {
            "status": "verified",
            "archive": archive_info,
            "access_date": access_date,
        }

    extract_dir = root / "extract"
    if not (extract_dir / ".extracted_ok").is_file():
        if extract_dir.exists():
            # Fresh extract to avoid partial trees
            import shutil

            shutil.rmtree(extract_dir)
        stats = safe_extract_zip(Path(archive_info["path"]), extract_dir)
        (extract_dir / ".extracted_ok").write_text(
            json.dumps(stats, sort_keys=True) + "\n", encoding="utf-8"
        )
    else:
        stats = json.loads((extract_dir / ".extracted_ok").read_text(encoding="utf-8"))

    prepared_dir = root / "prepared"
    subset = build_subset(
        extract_dir,
        prepared_dir,
        seed=seed,
        max_samples=None,
        light_cap=ASAP_LIGHT_CAP,
    )

    modification = default_modification_notice(
        access_date=access_date,
        subset_version=ASAP_SUBSET_VERSION,
        crop_transform_version=ASAP_CROP_TRANSFORM_VERSION,
        selected_count=int(subset["selected_count"]),
        rejected_count=int(subset["rejected_count"]),
    )
    licence_record = AsapLicenceRecord(
        title=DATASET_TITLE,
        creators=DATASET_CREATORS,
        doi=ZENODO_DOI,
        zenodo_record_id=ZENODO_RECORD_ID,
        licence_id=LICENCE_ID,
        licence_name=LICENCE_NAME,
        licence_url=LICENCE_URL,
        access_date=access_date,
        archive_filename=ARCHIVE_FILENAME,
        official_md5=OFFICIAL_MD5,
        local_sha256=str(archive_info["sha256"]),
        archive_bytes=int(archive_info["bytes"]),
        attribution=ATTRIBUTION_TEXT,
        modification_notice=modification,
    )
    prov_dir = root / "provenance"
    prov_dir.mkdir(parents=True, exist_ok=True)
    (prov_dir / "licence-record.json").write_text(
        json.dumps(licence_record.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return {
        "status": "prepared",
        "data_root": str(root),
        "archive": archive_info,
        "extract": stats,
        "subset": {
            "subset_version": subset["subset_version"],
            "transform_version": subset["transform_version"],
            "selected_count": subset["selected_count"],
            "light_count": subset["light_count"],
            "rejected_count": subset["rejected_count"],
            "exact_duplicates": subset["exact_duplicates"],
            "prompt_group_count": subset["prompt_group_count"],
            "subset_manifest_sha256": subset.get("subset_manifest_sha256"),
            "written_manifest_sha256": subset.get("written_manifest_sha256"),
            "zenodo_record_url": ZENODO_RECORD_URL,
            "dataset_version": DATASET_VERSION,
        },
        "licence_record": licence_record.to_dict(),
    }

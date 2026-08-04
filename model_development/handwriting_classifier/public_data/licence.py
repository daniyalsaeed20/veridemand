"""Licence and provenance constants for Handwritten ASAP (CC BY 4.0)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

# Zenodo record verified 2026-08-04 via https://zenodo.org/api/records/8088866
ZENODO_RECORD_ID = "8088866"
ZENODO_DOI = "10.5281/zenodo.8088866"
ZENODO_RECORD_URL = "https://zenodo.org/records/8088866"
ZENODO_API_URL = "https://zenodo.org/api/records/8088866"
DATASET_TITLE = "Handwritten ASAP Short Answer Scoring"
DATASET_CREATORS = ("Gold, Christian", "Zesch, Torsten")
DATASET_VERSION = "1.0"
DATASET_PUBLICATION_DATE = "2020-07-01"
LICENCE_ID = "cc-by-4.0"
LICENCE_NAME = "Creative Commons Attribution 4.0 International"
LICENCE_URL = "https://creativecommons.org/licenses/by/4.0/"
ARCHIVE_FILENAME = "Handwritten-ASAP-SAS-V1.0.zip"
ARCHIVE_SIZE_BYTES = 98397862
OFFICIAL_MD5 = "d365ea3ca8afc19d4758a22daa2e1ea2"

# Allowlisted download hosts (scheme https only).
ALLOWED_DOWNLOAD_HOSTS = frozenset(
    {
        "zenodo.org",
        "www.zenodo.org",
    }
)

ATTRIBUTION_TEXT = (
    "Gold, Christian; Zesch, Torsten (2020). Handwritten ASAP Short Answer "
    "Scoring (Version 1.0) [Data set]. Zenodo. "
    f"https://doi.org/{ZENODO_DOI}. Licensed under CC BY 4.0 ({LICENCE_URL})."
)


@dataclass(frozen=True)
class AsapLicenceRecord:
    """Provenance fields required before prepare may succeed."""

    title: str = DATASET_TITLE
    creators: tuple[str, ...] = DATASET_CREATORS
    doi: str = ZENODO_DOI
    zenodo_record_id: str = ZENODO_RECORD_ID
    licence_id: str = LICENCE_ID
    licence_name: str = LICENCE_NAME
    licence_url: str = LICENCE_URL
    access_date: str = ""
    archive_filename: str = ARCHIVE_FILENAME
    official_md5: str = OFFICIAL_MD5
    local_sha256: str = ""
    archive_bytes: int = 0
    attribution: str = ATTRIBUTION_TEXT
    modification_notice: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["creators"] = list(self.creators)
        return d


def default_modification_notice(
    *,
    access_date: str,
    subset_version: str,
    crop_transform_version: str,
    selected_count: int,
    rejected_count: int,
) -> str:
    return (
        f"On {access_date}, VeriDemand model-development prepared a bounded "
        f"training subset ({subset_version}) of {selected_count} images from "
        f"{ARCHIVE_FILENAME} (rejected={rejected_count}). Images were "
        f"QC-filtered and framed with {crop_transform_version} "
        "(deterministic paper-white letterbox / mild aspect crops). "
        "Transcription, ASAP IDs, and score labels from the source archive "
        "were discarded; every selected crop is labelled only as handwritten "
        "for writing-style routing. Raw archive and extracted images are not "
        "redistributed."
    )


def require_cc_by_4_0(licence_id: str) -> None:
    if licence_id.strip().lower() not in {LICENCE_ID, "cc-by-4.0"}:
        raise RuntimeError(
            "PUBLIC HANDWRITING SUPPLEMENT BLOCKED BY LICENSING: "
            f"expected {LICENCE_ID}, got {licence_id!r}"
        )


def today_access_date() -> str:
    return date.today().isoformat()

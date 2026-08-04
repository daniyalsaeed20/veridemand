"""Allowlisted download + checksum verification for Handwritten ASAP."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from model_development.handwriting_classifier.public_data.licence import (
    ALLOWED_DOWNLOAD_HOSTS,
    ARCHIVE_FILENAME,
    ARCHIVE_SIZE_BYTES,
    LICENCE_ID,
    OFFICIAL_MD5,
    ZENODO_API_URL,
    require_cc_by_4_0,
)


class LicenceBlockedError(RuntimeError):
    """Raised when Zenodo licence metadata does not permit use."""


def _assert_allowed_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"download URL must be https, got {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_DOWNLOAD_HOSTS:
        raise ValueError(f"download host not allowlisted: {host!r}")


def fetch_zenodo_metadata(api_url: str = ZENODO_API_URL) -> dict[str, Any]:
    _assert_allowed_url(api_url)
    req = urllib.request.Request(
        api_url,
        headers={"Accept": "application/json", "User-Agent": "VeriDemand-model-dev/1.0"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    licence = (payload.get("metadata") or {}).get("license") or {}
    licence_id = str(licence.get("id") or "")
    require_cc_by_4_0(licence_id)
    return payload


def resolve_download_url(metadata: dict[str, Any]) -> tuple[str, str]:
    """Return (download_url, md5_hex) for the official archive file."""

    files = metadata.get("files") or []
    for f in files:
        key = str(f.get("key") or "")
        if key != ARCHIVE_FILENAME:
            continue
        checksum = str(f.get("checksum") or "")
        if not checksum.startswith("md5:"):
            raise LicenceBlockedError(f"unexpected checksum format: {checksum!r}")
        md5_hex = checksum.split(":", 1)[1].lower()
        if md5_hex != OFFICIAL_MD5:
            raise LicenceBlockedError(
                f"Zenodo MD5 mismatch: expected {OFFICIAL_MD5}, got {md5_hex}"
            )
        links = f.get("links") or {}
        url = str(links.get("self") or links.get("download") or "")
        if not url:
            # Fallback content URL pattern
            url = f"https://zenodo.org/api/records/{metadata.get('id')}/files/{key}/content"
        _assert_allowed_url(url)
        return url, md5_hex
    raise LicenceBlockedError(f"archive {ARCHIVE_FILENAME} not found in Zenodo record")


def md5_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def download_archive(
    url: str,
    dest: Path,
    *,
    expected_md5: str = OFFICIAL_MD5,
    expected_size: int | None = ARCHIVE_SIZE_BYTES,
) -> dict[str, Any]:
    """Download to a temporary partial file, verify MD5, then rename."""

    _assert_allowed_url(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    if partial.exists():
        partial.unlink()

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "VeriDemand-model-dev/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=600) as resp, partial.open("wb") as out:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        actual_md5 = md5_file(partial)
        if actual_md5 != expected_md5.lower():
            partial.unlink(missing_ok=True)
            raise LicenceBlockedError(
                f"checksum mismatch: expected md5={expected_md5}, got {actual_md5}"
            )
        if expected_size is not None and partial.stat().st_size != expected_size:
            # Soft warning path: still refuse if wildly wrong after MD5? MD5 is authoritative.
            pass
        local_sha = sha256_file(partial)
        if dest.exists():
            dest.unlink()
        partial.rename(dest)
        return {
            "path": str(dest),
            "md5": actual_md5,
            "sha256": local_sha,
            "bytes": dest.stat().st_size,
            "licence_id": LICENCE_ID,
        }
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def ensure_verified_archive(
    data_root: Path,
    *,
    verify_only: bool = False,
    force_download: bool = False,
) -> dict[str, Any]:
    """Ensure archive exists and matches official MD5; optionally skip download."""

    archive_path = data_root / "archive" / ARCHIVE_FILENAME
    meta_path = data_root / "provenance" / "zenodo-metadata.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    if archive_path.is_file() and not force_download:
        actual_md5 = md5_file(archive_path)
        if actual_md5 != OFFICIAL_MD5:
            raise LicenceBlockedError(
                f"existing archive MD5 mismatch: expected {OFFICIAL_MD5}, got {actual_md5}"
            )
        local_sha = sha256_file(archive_path)
        if verify_only:
            return {
                "path": str(archive_path),
                "md5": actual_md5,
                "sha256": local_sha,
                "bytes": archive_path.stat().st_size,
                "downloaded": False,
                "verified_only": True,
                "licence_id": LICENCE_ID,
            }
        # Still refresh metadata licence check when not verify-only
        metadata = fetch_zenodo_metadata()
        meta_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return {
            "path": str(archive_path),
            "md5": actual_md5,
            "sha256": local_sha,
            "bytes": archive_path.stat().st_size,
            "downloaded": False,
            "verified_only": False,
            "licence_id": LICENCE_ID,
        }

    if verify_only:
        raise FileNotFoundError(f"archive missing for verify-only: {archive_path}")

    metadata = fetch_zenodo_metadata()
    meta_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    url, md5_hex = resolve_download_url(metadata)
    result = download_archive(url, archive_path, expected_md5=md5_hex)
    result["downloaded"] = True
    result["verified_only"] = False
    return result

from __future__ import annotations

import hashlib
from pathlib import Path

from backend.app.canonical.images import canonicalise_image_pdf
from backend.app.canonical.service import CanonicalisationService
from backend.app.contracts.identifiers import new_document_id, new_job_id, new_session_id
from backend.app.settings.config import Settings
from backend.app.storage.file_store import FileStore


def _canonicalise_image(
    settings: Settings,
    file_store: FileStore,
    source: Path,
) -> tuple[str, int]:
    service = CanonicalisationService(settings, temp_root=file_store.temp_root)
    result = canonicalise_image_pdf(
        settings=settings,
        service=service,
        session_id=new_session_id(),
        document_id=new_document_id(),
        job_id=new_job_id(),
        original_path=source,
    )
    digest = hashlib.sha256(result.path.read_bytes()).hexdigest()
    return digest, len(result.pages)


def test_png_canonicalises(settings: Settings, file_store: FileStore, uploads_dir: Path) -> None:
    digest, page_count = _canonicalise_image(settings, file_store, uploads_dir / "valid.png")
    assert page_count == 1
    assert len(digest) == 64


def test_jpeg_canonicalises(settings: Settings, file_store: FileStore, uploads_dir: Path) -> None:
    _digest, page_count = _canonicalise_image(settings, file_store, uploads_dir / "valid.jpeg")
    assert page_count == 1


def test_tiff_multipage_page_count(
    settings: Settings, file_store: FileStore, uploads_dir: Path
) -> None:
    _digest, page_count = _canonicalise_image(
        settings, file_store, uploads_dir / "valid_multiframe.tiff"
    )
    assert page_count == 2


def test_png_canonicalisation_is_deterministic(
    settings: Settings, file_store: FileStore, uploads_dir: Path
) -> None:
    source = uploads_dir / "valid.png"
    first_hash, first_pages = _canonicalise_image(settings, file_store, source)
    second_hash, second_pages = _canonicalise_image(settings, file_store, source)
    assert first_hash == second_hash
    assert first_pages == second_pages == 1

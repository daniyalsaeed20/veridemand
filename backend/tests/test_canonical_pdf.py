from __future__ import annotations

import hashlib
from pathlib import Path

from backend.app.canonical.pdf import canonicalise_original_pdf
from backend.app.canonical.service import CanonicalisationService
from backend.app.contracts.canonical import (
    CanonicalisationMethod,
    CanonicalPageMetadata,
    CanonicalPageSourceType,
)
from backend.app.contracts.identifiers import new_document_id, new_job_id, new_session_id
from backend.app.settings.config import Settings
from backend.app.storage.file_store import FileStore


def _canonicalise_pdf(
    settings: Settings,
    file_store: FileStore,
    source: Path,
) -> tuple[str, list[CanonicalPageMetadata]]:
    service = CanonicalisationService(settings, temp_root=file_store.temp_root)
    result = canonicalise_original_pdf(
        settings=settings,
        service=service,
        session_id=new_session_id(),
        document_id=new_document_id(),
        job_id=new_job_id(),
        original_path=source,
    )
    return result.sha256, result.pages


def test_original_pdf_preserves_bytes(
    settings: Settings, file_store: FileStore, uploads_dir: Path
) -> None:
    source = uploads_dir / "valid_single_page.pdf"
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    canonical_hash, pages = _canonicalise_pdf(settings, file_store, source)
    assert canonical_hash == original_hash
    assert len(pages) == 1
    assert pages[0].source_type is CanonicalPageSourceType.PDF


def test_multi_page_pdf_metadata(
    settings: Settings, file_store: FileStore, uploads_dir: Path
) -> None:
    source = uploads_dir / "valid_multi_page.pdf"
    _canonical_hash, pages = _canonicalise_pdf(settings, file_store, source)
    assert len(pages) == 3
    assert [page.page_number for page in pages] == [1, 2, 3]
    assert all(page.width_points > 0 for page in pages)
    assert all(page.height_points > 0 for page in pages)


def test_original_pdf_method_is_original(
    settings: Settings, file_store: FileStore, uploads_dir: Path
) -> None:
    service = CanonicalisationService(settings, temp_root=file_store.temp_root)
    result = canonicalise_original_pdf(
        settings=settings,
        service=service,
        session_id=new_session_id(),
        document_id=new_document_id(),
        job_id=new_job_id(),
        original_path=uploads_dir / "valid_single_page.pdf",
    )
    assert result.method is CanonicalisationMethod.ORIGINAL_PDF

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from backend.app.canonical.errors import CanonicalisationError
from backend.app.canonical.service import CanonicalisationService
from backend.app.canonical.text import canonicalise_text_pdf
from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.identifiers import new_document_id, new_job_id, new_session_id
from backend.app.settings.config import Settings
from backend.app.storage.file_store import FileStore


def _canonicalise_txt(
    settings: Settings,
    file_store: FileStore,
    source: Path,
) -> tuple[str, int]:
    service = CanonicalisationService(settings, temp_root=file_store.temp_root)
    result, _encoding = canonicalise_text_pdf(
        settings=settings,
        service=service,
        session_id=new_session_id(),
        document_id=new_document_id(),
        job_id=new_job_id(),
        original_path=source,
    )
    digest = hashlib.sha256(result.path.read_bytes()).hexdigest()
    return digest, len(result.pages)


def test_txt_to_pdf_is_deterministic(
    settings: Settings, file_store: FileStore, uploads_dir: Path
) -> None:
    source = uploads_dir / "valid_utf8.txt"
    first_hash, first_pages = _canonicalise_txt(settings, file_store, source)
    second_hash, second_pages = _canonicalise_txt(settings, file_store, source)
    assert first_hash == second_hash
    assert first_pages == second_pages == 1


def test_crlf_normalisation_is_deterministic(
    settings: Settings, file_store: FileStore, tmp_path: Path
) -> None:
    source = tmp_path / "crlf.txt"
    source.write_bytes(b"line one\r\nline two\r\n")
    first_hash, _ = _canonicalise_txt(settings, file_store, source)
    lf_source = tmp_path / "lf.txt"
    lf_source.write_bytes(b"line one\nline two\n")
    second_hash, _ = _canonicalise_txt(settings, file_store, lf_source)
    assert first_hash == second_hash


def test_unsupported_glyph_raises_error(
    settings: Settings, file_store: FileStore, tmp_path: Path
) -> None:
    source = tmp_path / "emoji.txt"
    source.write_text("Hello \U0001f600", encoding="utf-8")
    service = CanonicalisationService(settings, temp_root=file_store.temp_root)
    with pytest.raises(CanonicalisationError) as exc_info:
        canonicalise_text_pdf(
            settings=settings,
            service=service,
            session_id=new_session_id(),
            document_id=new_document_id(),
            job_id=new_job_id(),
            original_path=source,
        )
    assert exc_info.value.code is ErrorCode.CANONICALISATION_UNSUPPORTED_TEXT_GLYPH

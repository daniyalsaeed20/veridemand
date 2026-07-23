from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.canonical.errors import CanonicalisationError
from backend.app.canonical.libreoffice import LibreOfficeService
from backend.app.canonical.service import CanonicalisationService
from backend.app.canonical.word import canonicalise_word_pdf
from backend.app.contracts.documents import DocumentFormat
from backend.app.contracts.identifiers import new_document_id, new_job_id, new_session_id
from backend.app.settings.config import Settings
from backend.app.storage.file_store import FileStore

_LO_PATH = Path(r"D:\programming\tools\libreoffice\program\soffice.com")
_LIBREOFFICE_SOURCE = Path(__file__).resolve().parents[1] / "app" / "canonical" / "libreoffice.py"


def _settings_with_libreoffice(tmp_path: Path) -> Settings | None:
    if _LO_PATH.is_file():
        return Settings(
            temp_root=tmp_path / "temp",
            libreoffice_executable=str(_LO_PATH),
            ocr_enabled=False,
        )
    probe = Settings(temp_root=tmp_path / "temp", ocr_enabled=False)
    try:
        LibreOfficeService(probe).resolve()
    except CanonicalisationError:
        return None
    return probe


def test_libreoffice_discovery_resolves(tmp_path: Path) -> None:
    settings = _settings_with_libreoffice(tmp_path)
    if settings is None:
        pytest.skip("LibreOffice is not available on this machine.")
    runtime = LibreOfficeService(settings).resolve()
    assert runtime.executable.is_file()
    assert "LibreOffice" in runtime.version


def test_libreoffice_converts_minimal_docx(tmp_path: Path, uploads_dir: Path) -> None:
    base = _settings_with_libreoffice(tmp_path)
    if base is None:
        pytest.skip("LibreOffice is not available on this machine.")
    # Keep an empty configured path when discovery used PATH (CI/Linux);
    # do not fall back to a developer Windows install path.
    settings = Settings(
        temp_root=base.temp_root,
        libreoffice_executable=base.libreoffice_executable,
        libreoffice_timeout_seconds=120.0,
        ocr_enabled=False,
    )

    file_store = FileStore(settings.temp_root)
    session_id = new_session_id()
    document_id = new_document_id()
    job_id = new_job_id()
    file_store.create_session_storage(session_id)
    service = CanonicalisationService(settings, temp_root=file_store.temp_root)
    libreoffice = LibreOfficeService(settings)
    source = uploads_dir / "valid_minimal.docx"
    # Copy into originals so conversion uses a session-owned path.
    original = file_store.original_path(session_id, document_id, "docx")
    original.write_bytes(source.read_bytes())

    result = canonicalise_word_pdf(
        settings=settings,
        service=service,
        libreoffice=libreoffice,
        session_id=session_id,
        document_id=document_id,
        job_id=job_id,
        original_path=original,
        fmt=DocumentFormat.DOCX,
    )

    assert result.path.is_file()
    assert result.path.read_bytes().startswith(b"%PDF")
    assert result.libreoffice_version
    assert len(result.pages) >= 1
    assert result.method.value == "libreoffice_writer_pdf"


def test_libreoffice_module_never_uses_shell_true() -> None:
    source = _LIBREOFFICE_SOURCE.read_text(encoding="utf-8")
    assert "shell=True" not in source


def test_readiness_pass_includes_libreoffice(tmp_path: Path) -> None:
    settings = _settings_with_libreoffice(tmp_path)
    if settings is None:
        pytest.skip("LibreOffice is not available on this machine.")

    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    checks = {item["name"]: item for item in response.json()["checks"]}
    assert checks["libreoffice"]["required"] is True
    assert checks["libreoffice"]["status"] == "pass"

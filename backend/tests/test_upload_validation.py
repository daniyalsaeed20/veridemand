from __future__ import annotations

import io
from pathlib import Path

import pytest
from starlette.datastructures import Headers, UploadFile

from backend.app.contracts.documents import DocumentSummary
from backend.app.contracts.uploads import RejectedDocument
from backend.app.settings.config import Settings
from backend.app.storage.file_store import FileStore
from backend.app.uploads.service import UploadService

from .conftest import build_runtime


def _upload_file(path: Path) -> UploadFile:
    data = path.read_bytes()
    return UploadFile(
        filename=path.name,
        file=io.BytesIO(data),
        size=len(data),
        headers=Headers({"content-type": "application/octet-stream"}),
    )


async def _run_single(
    settings: Settings, file_store: FileStore, path: Path
) -> tuple[list[DocumentSummary], list[RejectedDocument]]:
    registry, _queue, _fs = build_runtime(settings)
    session = await registry.create()
    service = UploadService(settings, file_store)
    return await service.process_batch(session, [_upload_file(path)])


async def test_every_fixture_matches_manifest(
    settings: Settings,
    file_store: FileStore,
    uploads_dir: Path,
    upload_manifest: list[dict[str, object]],
) -> None:
    failures: list[str] = []
    for item in upload_manifest:
        name = str(item["filename"])
        accepted, rejected = await _run_single(settings, file_store, uploads_dir / name)
        if item["outcome"] == "accepted":
            if len(accepted) != 1 or rejected:
                failures.append(f"{name}: expected accepted, got {accepted=} {rejected=}")
        else:
            if len(rejected) != 1 or accepted:
                failures.append(f"{name}: expected rejected, got {accepted=} {rejected=}")
            elif rejected[0].error_code != item["error_code"]:
                failures.append(
                    f"{name}: expected {item['error_code']}, got {rejected[0].error_code}"
                )
    assert not failures, "\n".join(failures)


async def test_accepted_pdf_reports_page_count(
    settings: Settings, file_store: FileStore, uploads_dir: Path
) -> None:
    accepted, rejected = await _run_single(
        settings, file_store, uploads_dir / "valid_multi_page.pdf"
    )
    assert not rejected
    assert accepted[0].page_count == 3
    assert accepted[0].progress_percent == 5
    assert accepted[0].result_available is False
    assert accepted[0].extraction_performed is False


async def test_external_relationship_docx_accepted_with_warning(
    settings: Settings, file_store: FileStore, uploads_dir: Path
) -> None:
    accepted, rejected = await _run_single(
        settings, file_store, uploads_dir / "valid_external_rel.docx"
    )
    assert not rejected
    assert accepted[0].warning_count >= 1


async def test_doc_macro_detection_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    file_store: FileStore,
    uploads_dir: Path,
) -> None:
    import oletools.olevba as olevba

    class _MacroParser:
        def __init__(self, _target: str) -> None: ...

        def detect_vba_macros(self) -> bool:
            return True

        def close(self) -> None: ...

    monkeypatch.setattr(olevba, "VBA_Parser", _MacroParser)

    accepted, rejected = await _run_single(settings, file_store, uploads_dir / "valid.doc")
    assert not accepted
    assert rejected[0].error_code == "upload_macros_not_supported"


async def test_session_file_count_limit(
    settings: Settings, file_store: FileStore, uploads_dir: Path
) -> None:
    limited = settings.model_copy(update={"max_files_per_session": 1})
    registry, _queue, _fs = build_runtime(limited)
    session = await registry.create()
    service = UploadService(limited, file_store)

    accepted, rejected = await service.process_batch(
        session,
        [
            _upload_file(uploads_dir / "valid.png"),
            _upload_file(uploads_dir / "valid.jpeg"),
        ],
    )

    assert len(accepted) == 1
    assert len(rejected) == 1
    assert rejected[0].error_code == "session_limit_exceeded"


async def test_valid_survives_invalid_sibling(
    settings: Settings, file_store: FileStore, uploads_dir: Path
) -> None:
    registry, _queue, _fs = build_runtime(settings)
    session = await registry.create()
    service = UploadService(settings, file_store)

    accepted, rejected = await service.process_batch(
        session,
        [
            _upload_file(uploads_dir / "corrupt.pdf"),
            _upload_file(uploads_dir / "valid.png"),
        ],
    )

    assert len(accepted) == 1
    assert accepted[0].format.value == "png"
    assert len(rejected) == 1
    assert rejected[0].input_index == 0

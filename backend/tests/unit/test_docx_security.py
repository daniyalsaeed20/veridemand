"""DOCX path safety and macro rejection unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.domain_errors import UploadFileError
from app.models.taxonomies import ErrorCode
from app.services.documents.validation import assert_safe_zip_member_name, inspect_docx_zip
from tests.fixtures.upload_builders import (
    write_docx_with_entry,
    write_docx_with_vba_content_type,
    write_docx_with_vba_relationship,
    write_docx_with_vbaproject,
    write_macro_enabled_as_docx,
    write_minimal_docx,
)


@pytest.mark.parametrize(
    "name",
    [
        "/word/document.xml",
        "\\word\\document.xml",
        "C:\\word\\document.xml",
        "C:/word/document.xml",
        "\\\\server\\share\\file",
        "//server/share/file",
        "../word/document.xml",
        "word/../../file",
        "word/foo/../../../etc/passwd",
        "",
        "bad\x00name.xml",
    ],
)
def test_unsafe_zip_member_names_rejected(name: str) -> None:
    with pytest.raises(UploadFileError) as exc:
        assert_safe_zip_member_name(name)
    assert exc.value.error_code == ErrorCode.UPLOAD_CORRUPT_FILE


def test_safe_relative_member_ok() -> None:
    assert assert_safe_zip_member_name("word/document.xml") == "word/document.xml"
    assert assert_safe_zip_member_name("word\\document.xml") == "word/document.xml"


@pytest.mark.parametrize(
    "entry",
    [
        "/word/evil.xml",
        "../evil.xml",
        "word/../../evil.xml",
        "C:/evil.xml",
    ],
)
def test_docx_with_unsafe_entries_rejected(tmp_path: Path, entry: str) -> None:
    path = write_docx_with_entry(tmp_path / "unsafe.docx", entry)
    with pytest.raises(UploadFileError) as exc:
        inspect_docx_zip(path)
    assert exc.value.error_code == ErrorCode.UPLOAD_CORRUPT_FILE
    # Validator must not extract to disk
    assert not (tmp_path / "evil.xml").exists()
    assert list(tmp_path.glob("**/evil.xml")) == []


def test_clean_docx_accepted(tmp_path: Path) -> None:
    path = write_minimal_docx(tmp_path / "ok.docx")
    inspect_docx_zip(path)


def test_vbaproject_rejected(tmp_path: Path) -> None:
    path = write_docx_with_vbaproject(tmp_path / "macro.docx")
    with pytest.raises(UploadFileError) as exc:
        inspect_docx_zip(path)
    assert exc.value.error_code == ErrorCode.UPLOAD_MACROS_NOT_SUPPORTED
    assert "word/vba" not in exc.value.message.lower()
    assert "\\" not in exc.value.message


def test_vba_content_type_without_obvious_filename(tmp_path: Path) -> None:
    path = write_docx_with_vba_content_type(tmp_path / "ct.docx")
    with pytest.raises(UploadFileError) as exc:
        inspect_docx_zip(path)
    assert exc.value.error_code == ErrorCode.UPLOAD_MACROS_NOT_SUPPORTED


def test_vba_relationship_without_obvious_filename(tmp_path: Path) -> None:
    path = write_docx_with_vba_relationship(tmp_path / "rel.docx")
    with pytest.raises(UploadFileError) as exc:
        inspect_docx_zip(path)
    assert exc.value.error_code == ErrorCode.UPLOAD_MACROS_NOT_SUPPORTED


def test_renamed_docm_as_docx_rejected(tmp_path: Path) -> None:
    path = write_macro_enabled_as_docx(tmp_path / "renamed.docx")
    with pytest.raises(UploadFileError) as exc:
        inspect_docx_zip(path)
    assert exc.value.error_code == ErrorCode.UPLOAD_MACROS_NOT_SUPPORTED

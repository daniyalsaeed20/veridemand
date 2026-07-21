from __future__ import annotations

import pytest

from backend.app.uploads.filename import normalise_filename
from backend.app.uploads.rejection import UploadRejected


def test_strips_directory_components() -> None:
    result = normalise_filename("/etc/passwd/report.pdf", max_length=255)
    assert result.display == "report.pdf"
    assert result.extension == "pdf"


def test_strips_windows_directory_components() -> None:
    result = normalise_filename(r"C:\\Users\\x\\evil.DOCX", max_length=255)
    assert result.display == "evil.DOCX"
    assert result.extension == "docx"


def test_lowercases_only_the_extension() -> None:
    result = normalise_filename("Mixed.TXT", max_length=255)
    assert result.display == "Mixed.TXT"
    assert result.extension == "txt"


def test_uses_only_final_extension() -> None:
    result = normalise_filename("archive.tar.gz", max_length=255)
    assert result.extension == "gz"


def test_rejects_nul_byte() -> None:
    with pytest.raises(UploadRejected):
        normalise_filename("bad\x00name.pdf", max_length=255)


def test_rejects_empty_after_stripping() -> None:
    with pytest.raises(UploadRejected):
        normalise_filename("   ", max_length=255)


def test_rejects_over_length() -> None:
    with pytest.raises(UploadRejected):
        normalise_filename("a" * 300 + ".pdf", max_length=255)


def test_control_characters_removed() -> None:
    result = normalise_filename("re\u200bport\t.pdf", max_length=255)
    assert "\u200b" not in result.display
    assert "\t" not in result.display


def test_nfc_normalisation_applied() -> None:
    # "e" + combining acute accent normalises to the single NFC codepoint.
    result = normalise_filename("cafe\u0301.txt", max_length=255)
    assert result.display == "caf\u00e9.txt"

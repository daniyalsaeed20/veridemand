from __future__ import annotations

import pytest

from backend.app.contracts.documents import DocumentFormat
from backend.app.uploads import signatures


@pytest.mark.parametrize(
    ("head", "fmt", "expected"),
    [
        (b"%PDF-1.7\n...", DocumentFormat.PDF, True),
        (b"not a pdf", DocumentFormat.PDF, False),
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest", DocumentFormat.DOC, True),
        (b"PK\x03\x04rest", DocumentFormat.DOCX, True),
        (b"\x89PNG\r\n\x1a\n", DocumentFormat.PNG, True),
        (b"\xff\xd8\xff\xe0", DocumentFormat.JPEG, True),
        (b"II*\x00", DocumentFormat.TIFF, True),
        (b"MM\x00*", DocumentFormat.TIFF, True),
        (b"BM....", DocumentFormat.BMP, True),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", DocumentFormat.WEBP, True),
        (b"RIFF\x00\x00\x00\x00WAVE", DocumentFormat.WEBP, False),
        (b"anything", DocumentFormat.TXT, True),
    ],
)
def test_signature_matches(head: bytes, fmt: DocumentFormat, expected: bool) -> None:
    assert signatures.signature_matches(head, fmt) is expected


def test_detect_labels() -> None:
    assert signatures.detect(b"%PDF-1.4") == "pdf"
    assert signatures.detect(b"PK\x03\x04") == "zip"
    assert signatures.detect(b"\x89PNG\r\n\x1a\n") == "png"
    assert signatures.detect(b"plain text") is None


def test_looks_binary_detects_executables_and_archives() -> None:
    assert signatures.looks_binary(b"MZ\x90\x00") is True
    assert signatures.looks_binary(b"\x7fELF") is True
    assert signatures.looks_binary(b"PK\x03\x04") is True
    assert signatures.looks_binary(b"\x1f\x8b") is True


def test_looks_binary_false_for_plain_text() -> None:
    assert signatures.looks_binary(b"Hello, world") is False

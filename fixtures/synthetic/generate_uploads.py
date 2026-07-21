"""Generate synthetic, non-sensitive upload fixtures for Phase 1 tests.

Every fixture is produced deterministically here (no private documents are ever
committed). The accompanying ``MANIFEST.json`` records, per fixture, the expected
upload outcome (accepted or rejected + stable ``error_code``) so backend tests can
parametrise over the corpus without hard-coding paths.

Run from the repository root:

    .venv\\Scripts\\python.exe fixtures\\synthetic\\generate_uploads.py

The generated files under ``fixtures/synthetic/uploads/`` are committed; this
script exists so they can be regenerated and audited.
"""

from __future__ import annotations

import json
import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path

from backend.app.contracts.errors import ErrorCode
from PIL import Image
from pypdf import PdfWriter

OUT_DIR = Path(__file__).resolve().parent / "uploads"

# --- Open Packaging Conventions XML parts -----------------------------------

CONTENT_TYPES_WORD = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)

CONTENT_TYPES_MACRO = CONTENT_TYPES_WORD.replace(
    "wordprocessingml.document.main+xml",
    "wordprocessingml.document.macroEnabled.main+xml",
)

CONTENT_TYPES_NOT_WORD = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/xml"/>'
    "</Types>"
)

ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    "</Relationships>"
)

DOCUMENT_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body><w:p><w:r><w:t>Synthetic fixture</w:t></w:r></w:p></w:body></w:document>"
)

EXTERNAL_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId100" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
    'Target="https://example.invalid/resource" TargetMode="External"/>'
    "</Relationships>"
)


@dataclass(frozen=True)
class Fixture:
    filename: str
    outcome: str  # "accepted" | "rejected"
    error_code: str | None
    note: str


# --- PDF ---------------------------------------------------------------------


def write_pdf(path: Path, pages: int, *, encrypt: bool) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    if encrypt:
        writer.encrypt("fixture-password")
    with path.open("wb") as handle:
        writer.write(handle)


def write_corrupt_pdf(path: Path) -> None:
    # Valid %PDF marker (passes signature) but a structurally broken body.
    path.write_bytes(b"%PDF-1.4\nthis is not a valid PDF body and has no xref\n%%EOF\n")


# --- Images ------------------------------------------------------------------


def write_image(path: Path, fmt: str, size: tuple[int, int] = (16, 12)) -> None:
    image = Image.new("RGB", size, color=(90, 140, 200))
    image.save(path, format=fmt)


def write_multiframe_tiff(path: Path) -> None:
    frame_one = Image.new("RGB", (16, 12), color=(200, 90, 90))
    frame_two = Image.new("RGB", (16, 12), color=(90, 200, 120))
    frame_one.save(path, format="TIFF", save_all=True, append_images=[frame_two])


# --- DOCX (OPC ZIP) ----------------------------------------------------------


def write_zip(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            info = zipfile.ZipInfo(name)
            zf.writestr(info, data)


def base_docx_entries() -> list[tuple[str, bytes]]:
    return [
        ("[Content_Types].xml", CONTENT_TYPES_WORD.encode("utf-8")),
        ("_rels/.rels", ROOT_RELS.encode("utf-8")),
        ("word/document.xml", DOCUMENT_XML.encode("utf-8")),
    ]


# --- Legacy DOC (OLE2 / CFB) -------------------------------------------------

_SECTOR = 512
_FREESECT = 0xFFFFFFFF
_ENDOFCHAIN = 0xFFFFFFFE
_FATSECT = 0xFFFFFFFD


def _dir_entry(name: str, obj_type: int, *, child: int, start: int, size: int) -> bytes:
    raw = name.encode("utf-16-le") + b"\x00\x00"
    raw = raw.ljust(64, b"\x00")[:64]
    name_len = (len(name) + 1) * 2
    entry = bytearray(128)
    entry[0:64] = raw
    struct.pack_into("<H", entry, 64, name_len)
    entry[66] = obj_type
    entry[67] = 0x01  # colour: black
    struct.pack_into("<I", entry, 68, _FREESECT)  # left sibling
    struct.pack_into("<I", entry, 72, _FREESECT)  # right sibling
    struct.pack_into("<I", entry, 76, child)  # child
    struct.pack_into("<I", entry, 116, start)  # starting sector
    struct.pack_into("<Q", entry, 120, size)  # stream size
    return bytes(entry)


def write_synthetic_doc(path: Path) -> None:
    """Write a minimal valid OLE2 file containing a ``WordDocument`` stream."""

    header = bytearray(512)
    header[0:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    struct.pack_into("<H", header, 24, 0x003E)  # minor version
    struct.pack_into("<H", header, 26, 0x0003)  # major version (v3, 512-byte)
    struct.pack_into("<H", header, 28, 0xFFFE)  # little-endian byte order
    struct.pack_into("<H", header, 30, 0x0009)  # sector shift -> 512
    struct.pack_into("<H", header, 32, 0x0006)  # mini sector shift -> 64
    struct.pack_into("<I", header, 44, 1)  # number of FAT sectors
    struct.pack_into("<I", header, 48, 1)  # first directory sector
    struct.pack_into("<I", header, 56, 0x00001000)  # mini stream cutoff (4096)
    struct.pack_into("<I", header, 60, 2)  # first mini FAT sector
    struct.pack_into("<I", header, 64, 1)  # number of mini FAT sectors
    struct.pack_into("<I", header, 68, _ENDOFCHAIN)  # first DIFAT sector
    struct.pack_into("<I", header, 72, 0)  # number of DIFAT sectors
    # DIFAT array (109 entries) begins at offset 76.
    difat = [0] + [_FREESECT] * 108
    struct.pack_into("<109I", header, 76, *difat)

    # Sector 0: FAT.
    fat = [_FATSECT, _ENDOFCHAIN, _ENDOFCHAIN, _ENDOFCHAIN] + [_FREESECT] * 124
    sector_fat = struct.pack("<128I", *fat)

    word_content = b"\xec\xa5\xc1\x00" + b"\x00" * 36  # 40 bytes, plausible FIB start

    # Sector 1: directory (4 x 128-byte entries).
    root = _dir_entry("Root Entry", 0x05, child=1, start=3, size=64)
    word = _dir_entry("WordDocument", 0x02, child=_FREESECT, start=0, size=len(word_content))
    empty = bytes(128)
    sector_dir = root + word + empty + empty

    # Sector 2: mini FAT (one mini sector chain, terminated).
    mini_fat = [_ENDOFCHAIN] + [_FREESECT] * 127
    sector_minifat = struct.pack("<128I", *mini_fat)

    # Sector 3: mini stream container (mini sector 0 holds WordDocument content).
    sector_ministream = word_content.ljust(_SECTOR, b"\x00")

    path.write_bytes(bytes(header) + sector_fat + sector_dir + sector_minifat + sector_ministream)


def verify_doc(path: Path) -> None:
    import olefile

    if not olefile.isOleFile(str(path)):
        raise RuntimeError(f"{path.name}: not recognised as an OLE file")
    ole = olefile.OleFileIO(str(path))
    try:
        streams = {"/".join(p.lower() for p in entry) for entry in ole.listdir()}
    finally:
        ole.close()
    if "worddocument" not in streams:
        raise RuntimeError(f"{path.name}: missing WordDocument stream ({streams})")


# --- Generation --------------------------------------------------------------


def generate() -> list[Fixture]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fixtures: list[Fixture] = []

    def accept(name: str, note: str) -> None:
        fixtures.append(Fixture(name, "accepted", None, note))

    def reject(name: str, code: ErrorCode, note: str) -> None:
        fixtures.append(Fixture(name, "rejected", code.value, note))

    # Accepted PDFs.
    write_pdf(OUT_DIR / "valid_single_page.pdf", 1, encrypt=False)
    accept("valid_single_page.pdf", "Single blank page PDF.")
    write_pdf(OUT_DIR / "valid_multi_page.pdf", 3, encrypt=False)
    accept("valid_multi_page.pdf", "Three-page PDF (page counting).")

    # Accepted images.
    write_image(OUT_DIR / "valid.png", "PNG")
    accept("valid.png", "Small PNG.")
    write_image(OUT_DIR / "valid.jpeg", "JPEG")
    accept("valid.jpeg", "Small JPEG.")
    write_image(OUT_DIR / "valid.bmp", "BMP")
    accept("valid.bmp", "Small BMP.")
    write_image(OUT_DIR / "valid.webp", "WEBP")
    accept("valid.webp", "Small WebP.")
    write_multiframe_tiff(OUT_DIR / "valid_multiframe.tiff")
    accept("valid_multiframe.tiff", "Two-frame TIFF.")

    # Accepted text.
    (OUT_DIR / "valid_utf8.txt").write_text("Hello, synthetic UTF-8 fixture.\n", encoding="utf-8")
    accept("valid_utf8.txt", "UTF-8 text.")
    (OUT_DIR / "valid_utf16.txt").write_bytes("Hello, synthetic UTF-16 fixture.\n".encode("utf-16"))
    accept("valid_utf16.txt", "UTF-16 (BOM) text.")

    # Accepted DOCX.
    write_zip(OUT_DIR / "valid_minimal.docx", base_docx_entries())
    accept("valid_minimal.docx", "Minimal valid WordprocessingML package.")
    write_zip(
        OUT_DIR / "valid_external_rel.docx",
        [*base_docx_entries(), ("word/_rels/document.xml.rels", EXTERNAL_RELS.encode("utf-8"))],
    )
    accept("valid_external_rel.docx", "Valid DOCX with an external relationship (warning marker).")

    # Accepted legacy DOC.
    write_synthetic_doc(OUT_DIR / "valid.doc")
    verify_doc(OUT_DIR / "valid.doc")
    accept("valid.doc", "Synthetic minimal OLE2 Word document (no macros).")

    # Rejected PDFs.
    write_pdf(OUT_DIR / "encrypted.pdf", 1, encrypt=True)
    reject("encrypted.pdf", ErrorCode.UPLOAD_ENCRYPTED_PDF, "Password-protected PDF.")
    write_corrupt_pdf(OUT_DIR / "corrupt.pdf")
    reject("corrupt.pdf", ErrorCode.UPLOAD_CORRUPT_FILE, "PDF marker but broken body.")
    write_image(OUT_DIR / "signature_mismatch.pdf", "PNG")
    reject(
        "signature_mismatch.pdf",
        ErrorCode.UPLOAD_SIGNATURE_MISMATCH,
        "PNG bytes with a .pdf extension.",
    )

    # Rejected images.
    write_image(OUT_DIR / "signature_mismatch.png", "JPEG")
    reject(
        "signature_mismatch.png",
        ErrorCode.UPLOAD_SIGNATURE_MISMATCH,
        "JPEG bytes with a .png extension.",
    )

    # Rejected text.
    (OUT_DIR / "empty.txt").write_bytes(b"")
    reject("empty.txt", ErrorCode.UPLOAD_EMPTY_FILE, "Zero-byte file.")
    (OUT_DIR / "binary_in_text.txt").write_bytes(b"\xff\xd8\xff\xe0 JFIF binary masquerading")
    reject(
        "binary_in_text.txt",
        ErrorCode.UPLOAD_SIGNATURE_MISMATCH,
        "Binary signature inside a .txt file.",
    )
    (OUT_DIR / "control_chars.txt").write_bytes(b"\x01" * 60 + b"hello")
    reject(
        "control_chars.txt",
        ErrorCode.UPLOAD_CORRUPT_FILE,
        "Text with too many control characters.",
    )

    # Rejected unsupported type.
    (OUT_DIR / "unsupported.xyz").write_text("not a supported type", encoding="utf-8")
    reject("unsupported.xyz", ErrorCode.UPLOAD_UNSUPPORTED_TYPE, "Disallowed extension.")

    # Rejected DOCX variants.
    write_zip(
        OUT_DIR / "macro_vba.docx",
        [*base_docx_entries(), ("word/vbaProject.bin", b"\x00\x01macro-marker")],
    )
    reject(
        "macro_vba.docx", ErrorCode.UPLOAD_MACROS_NOT_SUPPORTED, "DOCX containing vbaProject.bin."
    )
    write_zip(
        OUT_DIR / "macro_content_type.docx",
        [
            ("[Content_Types].xml", CONTENT_TYPES_MACRO.encode("utf-8")),
            ("_rels/.rels", ROOT_RELS.encode("utf-8")),
            ("word/document.xml", DOCUMENT_XML.encode("utf-8")),
        ],
    )
    reject(
        "macro_content_type.docx",
        ErrorCode.UPLOAD_MACROS_NOT_SUPPORTED,
        "DOCX declaring a macro-enabled content type.",
    )
    write_zip(
        OUT_DIR / "unsafe_path.docx",
        [*base_docx_entries(), ("../evil.xml", b"traversal")],
    )
    reject("unsafe_path.docx", ErrorCode.UPLOAD_ARCHIVE_UNSAFE, "DOCX with a path-traversal entry.")
    write_zip(
        OUT_DIR / "not_wordml.docx",
        [
            ("[Content_Types].xml", CONTENT_TYPES_NOT_WORD.encode("utf-8")),
            ("_rels/.rels", ROOT_RELS.encode("utf-8")),
            ("word/document.xml", DOCUMENT_XML.encode("utf-8")),
        ],
    )
    reject(
        "not_wordml.docx", ErrorCode.UPLOAD_CORRUPT_FILE, "OPC ZIP that is not WordprocessingML."
    )
    (OUT_DIR / "corrupt.docx").write_bytes(b"PK\x03\x04 not a real zip archive body")
    reject("corrupt.docx", ErrorCode.UPLOAD_CORRUPT_FILE, "ZIP signature but malformed archive.")

    # Rejected legacy DOC.
    (OUT_DIR / "not_ole.doc").write_bytes(b"This is plainly not an OLE compound file.")
    reject(
        "not_ole.doc", ErrorCode.UPLOAD_SIGNATURE_MISMATCH, "Non-OLE bytes with a .doc extension."
    )

    return fixtures


def main() -> None:
    fixtures = generate()
    manifest = {
        "description": (
            "Synthetic, non-sensitive Phase 1 upload fixtures. Regenerate with "
            "fixtures/synthetic/generate_uploads.py. No private documents are included."
        ),
        "fixtures": [
            {
                "filename": fixture.filename,
                "outcome": fixture.outcome,
                "error_code": fixture.error_code,
                "note": fixture.note,
            }
            for fixture in sorted(fixtures, key=lambda item: item.filename)
        ],
    }
    (OUT_DIR / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Generated {len(fixtures)} fixtures in {OUT_DIR}")


if __name__ == "__main__":
    main()

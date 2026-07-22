"""Structural inspection of the canonical PDF with pypdf (not text extraction)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.contracts.errors import ErrorCode
from backend.app.extraction.native.errors import NativeExtractionError
from backend.app.extraction.native.models import CanonicalPageRef
from pypdf import PdfReader
from pypdf.errors import PdfReadError


@dataclass(frozen=True, slots=True)
class PageStructuralInfo:
    page_number: int
    width_points: float
    height_points: float
    rotation: int
    has_contents: bool
    content_stream_count: int | None


@dataclass(frozen=True, slots=True)
class StructuralInspectionResult:
    page_count: int
    pages: list[PageStructuralInfo]
    encrypted: bool


def _page_box_size(page: Any) -> tuple[float, float]:
    """Return effective width/height after intrinsic rotation (CropBox preferred)."""

    box = page.cropbox if page.cropbox is not None else page.mediabox
    width = float(box.width)
    height = float(box.height)
    rotation = int(page.rotation or 0) % 360
    if rotation in (90, 270):
        return height, width
    return width, height


def _content_info(page: Any) -> tuple[bool, int | None]:
    try:
        contents = page.get_contents()
    except Exception:
        return False, None
    if contents is None:
        return False, 0
    if isinstance(contents, list):
        return len(contents) > 0, len(contents)
    return True, 1


def inspect_canonical_pdf(
    pdf_path: Path,
    expected_pages: list[CanonicalPageRef],
    *,
    dimension_tolerance: float,
) -> StructuralInspectionResult:
    """Inspect the canonical PDF and compare against Phase 2 metadata."""

    try:
        reader = PdfReader(str(pdf_path))
    except PdfReadError as exc:
        raise NativeExtractionError(
            ErrorCode.NATIVE_EXTRACTION_FAILED,
            "The canonical PDF could not be opened for native inspection.",
        ) from exc
    except OSError as exc:
        raise NativeExtractionError(
            ErrorCode.NATIVE_EXTRACTION_FAILED,
            "The canonical PDF was not readable for native inspection.",
        ) from exc

    if reader.is_encrypted:
        raise NativeExtractionError(
            ErrorCode.NATIVE_EXTRACTION_FAILED,
            "The canonical PDF is encrypted and cannot be inspected.",
        )

    if len(reader.pages) != len(expected_pages):
        raise NativeExtractionError(
            ErrorCode.NATIVE_PAGE_METADATA_MISMATCH,
            "Canonical page count does not match the PDF structure.",
        )

    pages: list[PageStructuralInfo] = []
    for index, expected in enumerate(expected_pages):
        page = reader.pages[index]
        width, height = _page_box_size(page)
        rotation = int(page.rotation or 0) % 360
        has_contents, stream_count = _content_info(page)

        if abs(width - expected.width_points) > dimension_tolerance:
            raise NativeExtractionError(
                ErrorCode.NATIVE_PAGE_METADATA_MISMATCH,
                "Canonical page dimensions do not match the PDF structure.",
            )
        if abs(height - expected.height_points) > dimension_tolerance:
            raise NativeExtractionError(
                ErrorCode.NATIVE_PAGE_METADATA_MISMATCH,
                "Canonical page dimensions do not match the PDF structure.",
            )
        if rotation != (expected.intrinsic_rotation % 360):
            raise NativeExtractionError(
                ErrorCode.NATIVE_PAGE_METADATA_MISMATCH,
                "Canonical page rotation does not match the PDF structure.",
            )

        pages.append(
            PageStructuralInfo(
                page_number=expected.page_number,
                width_points=width,
                height_points=height,
                rotation=rotation,
                has_contents=has_contents,
                content_stream_count=stream_count,
            )
        )

    return StructuralInspectionResult(
        page_count=len(pages),
        pages=pages,
        encrypted=False,
    )

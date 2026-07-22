"""Canonical PDF inspection using pypdf (no text extraction)."""

from __future__ import annotations

from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from backend.app.canonical.errors import CanonicalisationError
from backend.app.contracts.canonical import CanonicalPageMetadata, CanonicalPageSourceType
from backend.app.contracts.errors import ErrorCode
from backend.app.geometry.validation import validate_rotation_degrees


@dataclass(frozen=True)
class _PageBox:
    width_points: float
    height_points: float


class CanonicalPdfInspectionService:
    """Inspect a canonical PDF and derive per-page geometry metadata."""

    def inspect_file(
        self,
        path: object,
        *,
        source_type: CanonicalPageSourceType,
        source_frame_index: int | None = None,
        source_pixel_width: int | None = None,
        source_pixel_height: int | None = None,
    ) -> list[CanonicalPageMetadata]:
        """Return page metadata for a readable, unencrypted PDF."""

        try:
            reader = PdfReader(str(path), strict=False)
        except (PdfReadError, OSError, ValueError, EOFError) as exc:
            raise CanonicalisationError(
                ErrorCode.CANONICALISATION_INVALID_PDF,
                "The canonical PDF could not be read.",
            ) from exc

        if reader.is_encrypted:
            raise CanonicalisationError(
                ErrorCode.CANONICALISATION_INVALID_PDF,
                "The canonical PDF is encrypted.",
            )

        if len(reader.pages) < 1:
            raise CanonicalisationError(
                ErrorCode.CANONICALISATION_INVALID_PDF,
                "The canonical PDF has no pages.",
            )

        pages: list[CanonicalPageMetadata] = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                rotation = validate_rotation_degrees(int(page.get("/Rotate", 0) or 0) % 360)
                box = self._effective_box(page)
                width, height = self._displayed_dimensions(box, rotation)
            except ValueError as exc:
                raise CanonicalisationError(
                    ErrorCode.CANONICALISATION_INVALID_PDF,
                    "The canonical PDF has invalid page geometry.",
                ) from exc

            if width <= 0 or height <= 0:
                raise CanonicalisationError(
                    ErrorCode.CANONICALISATION_INVALID_PDF,
                    "The canonical PDF has non-positive page dimensions.",
                )

            pages.append(
                CanonicalPageMetadata(
                    page_number=index,
                    width_points=width,
                    height_points=height,
                    intrinsic_rotation=rotation,
                    source_type=source_type,
                    source_frame_index=source_frame_index if index == 1 else None,
                    source_pixel_width=source_pixel_width if index == 1 else None,
                    source_pixel_height=source_pixel_height if index == 1 else None,
                    image_placement_bbox=None,
                )
            )
        return pages

    @staticmethod
    def _effective_box(page: object) -> _PageBox:
        """Use crop box when present, otherwise media box."""

        crop = page.cropbox  # type: ignore[attr-defined]
        media = page.mediabox  # type: ignore[attr-defined]
        box = crop if crop is not None else media
        left = float(box.left)
        bottom = float(box.bottom)
        right = float(box.right)
        top = float(box.top)
        width = right - left
        height = top - bottom
        if width <= 0 or height <= 0:
            raise ValueError("Invalid page box dimensions.")
        return _PageBox(width_points=width, height_points=height)

    @staticmethod
    def _displayed_dimensions(box: _PageBox, rotation: int) -> tuple[float, float]:
        if rotation in (90, 270):
            return box.height_points, box.width_points
        return box.width_points, box.height_points

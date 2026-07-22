"""Image → PDF canonicalisation using Pillow and ReportLab."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from backend.app.canonical.constants import (
    _FIXED_AUTHOR,
    _FIXED_CREATOR,
    _FIXED_PRODUCER,
    _FIXED_SUBJECT,
    _FIXED_TITLE,
)
from backend.app.canonical.errors import CanonicalisationError
from backend.app.canonical.models import CanonicalisationResult
from backend.app.canonical.service import CanonicalisationService
from backend.app.contracts.canonical import (
    CanonicalisationMethod,
    CanonicalPageMetadata,
    CanonicalPageSourceType,
)
from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.geometry import NormalisedBoundingBox
from backend.app.settings.config import Settings

_FULL_PAGE_BBOX = NormalisedBoundingBox(x=0.0, y=0.0, width=1.0, height=1.0)


def canonicalise_image_pdf(
    *,
    settings: Settings,
    service: CanonicalisationService,
    session_id: str,
    document_id: str,
    job_id: str,
    original_path: Path,
    warnings: list[str] | None = None,
) -> CanonicalisationResult:
    """Wrap one or more image frames into a canonical multi-page PDF."""

    staging_dir = service.staging_canonical_dir(session_id, job_id)
    staged_pdf = staging_dir / "image.pdf"
    page_metas = _render_image_pdf(original_path, staged_pdf, settings)
    try:
        result = service.publish_atomic(
            session_id=session_id,
            document_id=document_id,
            staging_pdf=staged_pdf,
            method=CanonicalisationMethod.REPORTLAB_IMAGE_PDF,
            source_type=CanonicalPageSourceType.IMAGE,
            warnings=warnings,
        )
        return _merge_image_metadata(result, page_metas)
    finally:
        service.cleanup_staging(session_id, job_id)


def _render_image_pdf(
    source: Path, destination: Path, settings: Settings
) -> list[CanonicalPageMetadata]:
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    dpi = settings.image_canonical_dpi
    max_points = settings.max_canonical_page_points
    Image.MAX_IMAGE_PIXELS = settings.max_image_pixels

    try:
        with Image.open(source) as image:
            if image.format == "WEBP" and int(getattr(image, "n_frames", 1)) > 1:
                raise CanonicalisationError(
                    ErrorCode.CANONICALISATION_MULTIFRAME_NOT_SUPPORTED,
                    "Animated WebP images are not supported.",
                )
            frame_count = int(getattr(image, "n_frames", 1))
            if frame_count < 1:
                raise CanonicalisationError(
                    ErrorCode.CANONICALISATION_FAILED,
                    "Image has no readable frames.",
                )
            if frame_count > 1 and image.format != "TIFF":
                raise CanonicalisationError(
                    ErrorCode.CANONICALISATION_MULTIFRAME_NOT_SUPPORTED,
                    "Multi-frame images are only supported for TIFF.",
                )

            buffer = BytesIO()
            pdf = canvas.Canvas(
                buffer,
                bottomup=1,
                invariant=True,
                pageCompression=0,
            )
            pdf.setTitle(_FIXED_TITLE)
            pdf.setAuthor(_FIXED_AUTHOR)
            pdf.setCreator(_FIXED_CREATOR)
            pdf.setProducer(_FIXED_PRODUCER)
            pdf.setSubject(_FIXED_SUBJECT)

            metas: list[CanonicalPageMetadata] = []
            for frame_index in range(frame_count):
                if frame_index > 0:
                    pdf.showPage()
                image.seek(frame_index)
                prepared = _prepare_frame(image)
                page_width, page_height = _page_size_points(prepared.size, dpi, max_points)
                pdf.setPageSize((page_width, page_height))
                reader = ImageReader(prepared)
                pdf.drawImage(
                    reader,
                    0,
                    0,
                    width=page_width,
                    height=page_height,
                )
                metas.append(
                    CanonicalPageMetadata(
                        page_number=frame_index + 1,
                        width_points=page_width,
                        height_points=page_height,
                        intrinsic_rotation=0,
                        source_type=CanonicalPageSourceType.IMAGE,
                        source_frame_index=frame_index,
                        source_pixel_width=prepared.width,
                        source_pixel_height=prepared.height,
                        image_placement_bbox=_FULL_PAGE_BBOX,
                    )
                )

            pdf.save()
            destination.write_bytes(buffer.getvalue())
            return metas
    except CanonicalisationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise CanonicalisationError(
            ErrorCode.CANONICALISATION_FAILED,
            "The image could not be canonicalised.",
        ) from exc


def _prepare_frame(image: Image.Image) -> Image.Image:
    corrected = ImageOps.exif_transpose(image) or image
    if corrected.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", corrected.size, "white")
        if corrected.mode == "P":
            corrected = corrected.convert("RGBA")
        background.paste(
            corrected,
            mask=corrected.split()[-1] if corrected.mode in ("RGBA", "LA") else None,
        )
        return background
    if corrected.mode != "RGB":
        return corrected.convert("RGB")
    return corrected


def _page_size_points(
    pixel_size: tuple[int, int], dpi: float, max_points: float
) -> tuple[float, float]:
    width_px, height_px = pixel_size
    width_points = (width_px / dpi) * 72.0
    height_points = (height_px / dpi) * 72.0
    scale = min(1.0, max_points / max(width_points, height_points))
    return width_points * scale, height_points * scale


def _merge_image_metadata(
    result: CanonicalisationResult,
    rendered: list[CanonicalPageMetadata],
) -> CanonicalisationResult:
    merged_pages: list[CanonicalPageMetadata] = []
    for inspected, source in zip(result.pages, rendered, strict=True):
        merged_pages.append(
            CanonicalPageMetadata(
                page_number=inspected.page_number,
                width_points=inspected.width_points,
                height_points=inspected.height_points,
                intrinsic_rotation=inspected.intrinsic_rotation,
                source_type=CanonicalPageSourceType.IMAGE,
                source_frame_index=source.source_frame_index,
                source_pixel_width=source.source_pixel_width,
                source_pixel_height=source.source_pixel_height,
                image_placement_bbox=source.image_placement_bbox,
            )
        )
    return CanonicalisationResult(
        pages=merged_pages,
        method=result.method,
        sha256=result.sha256,
        size_bytes=result.size_bytes,
        path=result.path,
        libreoffice_version=result.libreoffice_version,
        warnings=result.warnings,
    )

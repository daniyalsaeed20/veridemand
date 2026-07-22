"""Canonical document contracts (Phase 2)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from backend.app.contracts.base import ApiModel
from backend.app.contracts.geometry import Geometry, NormalisedBoundingBox
from backend.app.contracts.identifiers import DocumentId


class CanonicalStatus(StrEnum):
    """Lifecycle of a document's canonical visual representation."""

    PENDING = "pending"
    QUEUED = "queued"
    CANONICALISING = "canonicalising"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CanonicalisationMethod(StrEnum):
    """How the canonical PDF was produced."""

    ORIGINAL_PDF = "original_pdf"
    LIBREOFFICE_WRITER_PDF = "libreoffice_writer_pdf"
    REPORTLAB_TEXT_PDF = "reportlab_text_pdf"
    REPORTLAB_IMAGE_PDF = "reportlab_image_pdf"


class CanonicalPageSourceType(StrEnum):
    """Origin of a canonical page's visual content."""

    PDF = "pdf"
    TEXT = "text"
    IMAGE = "image"
    WORD = "word"


class CanonicalPageMetadata(ApiModel):
    """Per-page geometry for the canonical PDF."""

    page_number: int = Field(ge=1, description="1-based page number.")
    width_points: float = Field(gt=0, description="Effective displayed width in PDF points.")
    height_points: float = Field(gt=0, description="Effective displayed height in PDF points.")
    intrinsic_rotation: int = Field(
        description="Intrinsic PDF page rotation already applied in the default visual system."
    )
    source_type: CanonicalPageSourceType = Field(description="Source material for this page.")
    source_frame_index: int | None = Field(
        default=None, ge=0, description="0-based source frame index for image-backed pages."
    )
    source_pixel_width: int | None = Field(
        default=None, gt=0, description="Source pixel width for image-backed pages."
    )
    source_pixel_height: int | None = Field(
        default=None, gt=0, description="Source pixel height for image-backed pages."
    )
    image_placement_bbox: NormalisedBoundingBox | None = Field(
        default=None,
        description="Normalised placement of the source image on the page (full-page when set).",
    )


class CanonicalDocumentMetadata(ApiModel):
    """Public metadata for a ready canonical document (no filesystem paths)."""

    document_id: DocumentId = Field(description="Opaque document identifier.")
    canonical_status: CanonicalStatus = Field(description="Canonicalisation lifecycle status.")
    canonicalisation_method: CanonicalisationMethod = Field(
        description="Method used to produce the canonical PDF."
    )
    media_type: str = Field(description="Always application/pdf for the canonical view.")
    size_bytes: int = Field(ge=0, description="Canonical PDF size in bytes.")
    sha256: str = Field(min_length=64, max_length=64, description="Lowercase hex SHA-256 digest.")
    page_count: int = Field(ge=1, description="Canonical page count.")
    pages: list[CanonicalPageMetadata] = Field(description="Per-page metadata.")
    created_at: datetime = Field(description="Timezone-aware UTC time the canonical PDF was ready.")
    libreoffice_version: str | None = Field(
        default=None, description="LibreOffice version when used for conversion."
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal warning codes from canonicalisation."
    )


class OverlayProofItem(ApiModel):
    """A single synthetic overlay used only for Phase 2 alignment verification."""

    id: str = Field(description="Stable overlay identifier.")
    label: str = Field(description="Human-readable label.")
    source: str = Field(description="Provenance marker; always synthetic_phase_2.")
    synthetic: bool = Field(description="Always true; this is not extraction output.")
    page_number: int = Field(ge=1, description="1-based page number.")
    geometry: Geometry = Field(description="Normalised geometry on the canonical page.")


class OverlayProofResponse(ApiModel):
    """Synthetic alignment overlays for every canonical page."""

    document_id: DocumentId = Field(description="Opaque document identifier.")
    synthetic: bool = Field(default=True, description="Always true for Phase 2 overlay proofs.")
    overlays: list[OverlayProofItem] = Field(description="One overlay per canonical page.")


# Fixed Phase 2 alignment-test geometry (top-left normalised visual coordinates).
PHASE2_ALIGNMENT_BBOX = NormalisedBoundingBox(x=0.10, y=0.15, width=0.25, height=0.10)

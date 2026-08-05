"""Page-level vision-reservation contracts (Phase 5 Task C3).

Conservative reservation marks image-dominant pages for future Phase 6 vision
processing. Phase 5 does not call a vision provider or produce transcription.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from backend.app.contracts.base import ApiModel
from backend.app.contracts.geometry import NormalisedBoundingBox


class PageVisionReservationStatus(StrEnum):
    """Whether a page requires deferred Phase 6 vision processing."""

    NOT_REQUIRED = "not_required"
    RESERVED_PENDING_PHASE_6 = "reserved_pending_phase_6"


class PageVisionReservationReason(StrEnum):
    """Why a page was reserved for Phase 6 (not a handwriting proof claim)."""

    IMAGE_DOMINANT = "image_dominant"


class PageVisionReservationScope(StrEnum):
    """Geometry scope retained for Phase 6."""

    FULL_PAGE = "full_page"


class LocalRecognitionPolicy(StrEnum):
    """Whether local Paddle recognition may run on this page."""

    ALLOWED = "allowed"
    PROHIBITED = "prohibited"


class PageVisionReservationEvidence(ApiModel):
    """Privacy-safe page reservation evidence (no provider payload or text)."""

    required: bool = False
    status: PageVisionReservationStatus = PageVisionReservationStatus.NOT_REQUIRED
    reason: PageVisionReservationReason | None = None
    scope: PageVisionReservationScope | None = None
    local_recognition_policy: LocalRecognitionPolicy = LocalRecognitionPolicy.ALLOWED
    full_page_bbox_normalized: NormalisedBoundingBox | None = None
    page_render_available: bool = False

    @model_validator(mode="after")
    def _consistent(self) -> PageVisionReservationEvidence:
        if not self.required:
            if self.status is not PageVisionReservationStatus.NOT_REQUIRED:
                raise ValueError("required=false requires status=not_required.")
            if self.reason is not None or self.scope is not None:
                raise ValueError("required=false must not set reason or scope.")
            if self.local_recognition_policy is not LocalRecognitionPolicy.ALLOWED:
                raise ValueError("required=false requires local_recognition_policy=allowed.")
            return self

        if self.status is not PageVisionReservationStatus.RESERVED_PENDING_PHASE_6:
            raise ValueError("required=true requires status=reserved_pending_phase_6.")
        if self.reason is None:
            raise ValueError("required=true requires a reservation reason.")
        if self.scope is not PageVisionReservationScope.FULL_PAGE:
            raise ValueError("required=true requires scope=full_page.")
        if self.local_recognition_policy is not LocalRecognitionPolicy.PROHIBITED:
            raise ValueError("required=true requires local_recognition_policy=prohibited.")
        if self.full_page_bbox_normalized is None:
            raise ValueError("required=true requires full_page_bbox_normalized.")
        bbox = self.full_page_bbox_normalized
        if (
            abs(bbox.x) > 1e-9
            or abs(bbox.y) > 1e-9
            or abs(bbox.width - 1.0) > 1e-9
            or abs(bbox.height - 1.0) > 1e-9
        ):
            raise ValueError("full_page_bbox_normalized must be the full page [0,0,1,1].")
        return self


def full_page_bbox() -> NormalisedBoundingBox:
    """Canonical full-page normalised geometry (origin top-left)."""

    return NormalisedBoundingBox(x=0.0, y=0.0, width=1.0, height=1.0)


def reserved_pending_phase_6_evidence(
    *,
    page_render_available: bool,
    reason: PageVisionReservationReason = PageVisionReservationReason.IMAGE_DOMINANT,
) -> PageVisionReservationEvidence:
    """Build conservative full-page reservation evidence."""

    return PageVisionReservationEvidence(
        required=True,
        status=PageVisionReservationStatus.RESERVED_PENDING_PHASE_6,
        reason=reason,
        scope=PageVisionReservationScope.FULL_PAGE,
        local_recognition_policy=LocalRecognitionPolicy.PROHIBITED,
        full_page_bbox_normalized=full_page_bbox(),
        page_render_available=page_render_available,
    )


def not_required_reservation_evidence() -> PageVisionReservationEvidence:
    """Default evidence when page-level reservation is not required."""

    return PageVisionReservationEvidence(
        required=False,
        status=PageVisionReservationStatus.NOT_REQUIRED,
        local_recognition_policy=LocalRecognitionPolicy.ALLOWED,
        page_render_available=False,
    )


# Re-export Annotated for callers that need typed lists without importing typing.
FullPageBBox = Annotated[NormalisedBoundingBox, Field(description="Full-page [0,0,1,1] bbox.")]

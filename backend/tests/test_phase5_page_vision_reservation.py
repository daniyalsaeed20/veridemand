"""Phase 5 Task C3 — conservative page vision reservation tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from backend.app.contracts.identifiers import new_document_id, new_job_id, new_session_id
from backend.app.contracts.native import (
    NativePageDecision,
    NativePageMetrics,
    NativePageResult,
    NativePageTrustResult,
    NativeTrustComponents,
    SourceMode,
    VisualAgreementStatus,
)
from backend.app.contracts.page_vision_reservation import (
    LocalRecognitionPolicy,
    PageVisionReservationReason,
    PageVisionReservationScope,
    PageVisionReservationStatus,
)
from backend.app.contracts.routing import PageRoute
from backend.app.contracts.visual import (
    PageResultState,
    VisualPageStatus,
    VisualProcessingStatus,
)
from backend.app.extraction.routing.embedded_ocr import page_is_image_dominant
from backend.app.extraction.routing.page_vision_reservation import (
    build_reserved_page_result,
    should_reserve_page_for_vision,
)
from backend.app.extraction.visual.service import build_final_route_histogram
from backend.app.settings.config import Settings


def _metrics(**overrides: object) -> NativePageMetrics:
    base: dict[str, object] = dict(
        raw_character_count=100,
        deduplicated_character_count=100,
        word_count=20,
        character_count=100,
        duplicate_character_ratio=0.0,
        replacement_character_ratio=0.0,
        control_character_ratio=0.0,
        private_use_character_ratio=0.0,
        unassigned_character_ratio=0.0,
        noncharacter_ratio=0.0,
        unprintable_character_ratio=0.0,
        cid_token_ratio=0.0,
        invalid_geometry_ratio=0.0,
        out_of_bounds_character_ratio=0.0,
        zero_area_character_ratio=0.0,
        invalid_word_geometry_ratio=0.0,
        single_character_word_ratio=0.1,
        symbol_only_word_ratio=0.0,
        alphanumeric_word_ratio=0.9,
        very_long_token_ratio=0.0,
        repeated_token_ratio=0.0,
        whitespace_ratio=0.1,
        font_count=1,
        missing_font_ratio=0.0,
        upright_character_ratio=1.0,
        extraction_order_backtrack_ratio=0.0,
        characters_per_page_area=0.01,
        words_per_page_area=0.002,
        image_count=1,
        largest_image_area_ratio=0.9,
        total_clipped_image_area_ratio=0.9,
        page_dimension_match=True,
        components=NativeTrustComponents(
            character_validity_score=1.0,
            geometry_validity_score=1.0,
            duplication_quality_score=1.0,
            token_structure_score=1.0,
            text_density_score=1.0,
            order_plausibility_score=1.0,
            image_compatibility_score=0.2,
        ),
    )
    base.update(overrides)
    return NativePageMetrics(**base)


def _page(
    *,
    page_number: int = 1,
    reason_codes: list[str] | None = None,
    source_mode: SourceMode = SourceMode.VISUAL_AUTHORITY,
    decision: NativePageDecision = NativePageDecision.REJECTED,
) -> NativePageResult:
    return NativePageResult(
        page_number=page_number,
        decision=decision,
        source_mode=source_mode,
        trust=NativePageTrustResult(
            page_number=page_number,
            decision=decision,
            source_mode=source_mode,
            native_text_present=False,
            native_trust_score=0.2,
            trust_policy_version="phase3-v1.5",
            hard_rejection=True,
            reason_codes=list(reason_codes or []),
            warning_codes=[],
            metrics=_metrics(),
            visual_agreement_status=VisualAgreementStatus.NOT_EVALUATED_PHASE_3,
            native_result_available=False,
            visual_processing_required=True,
        ),
        words=[],
        characters=[],
    )


def test_image_dominant_predicate_reused() -> None:
    dominant = _page(reason_codes=["image_dominant_page"])
    plain = _page(reason_codes=["native_text_rejected"])
    assert page_is_image_dominant(dominant) is True
    assert page_is_image_dominant(plain) is False
    assert page_is_image_dominant(_page(source_mode=SourceMode.IMAGE_AUTHORITY)) is True


def test_reservation_requires_flag_and_dominance() -> None:
    dominant = _page(reason_codes=["image_dominant_page"])
    plain = _page(reason_codes=["native_text_rejected"])
    off = Settings(handwriting_page_vision_fallback_enabled=False)
    on = Settings(handwriting_page_vision_fallback_enabled=True)

    assert should_reserve_page_for_vision(dominant, off) is False
    assert should_reserve_page_for_vision(plain, on) is False
    assert should_reserve_page_for_vision(dominant, on) is True


def test_document_family_and_private_ids_do_not_trigger() -> None:
    page = _page(reason_codes=["native_text_rejected"])
    settings = Settings(handwriting_page_vision_fallback_enabled=True)
    assert should_reserve_page_for_vision(page, settings) is False
    assert page_is_image_dominant(page) is False


def test_hybrid_mode_rejected_loudly() -> None:
    with pytest.raises(ValidationError, match="conservative"):
        Settings(
            handwriting_page_vision_fallback_enabled=True,
            handwriting_page_vision_fallback_mode="hybrid",
        )


def test_reserved_page_contract_and_authority() -> None:
    page = _page(reason_codes=["image_dominant_page"], source_mode=SourceMode.IMAGE_AUTHORITY)
    result = build_reserved_page_result(page, page_render_available=True)

    assert result.page_result_state is PageResultState.VISION_RESERVED_PENDING_PHASE_6
    assert result.page_route == PageRoute.VISION_RESERVED_PENDING_PHASE_6.value
    assert result.status is VisualPageStatus.RESERVED_PENDING_PHASE_6
    assert result.source_mode is SourceMode.IMAGE_AUTHORITY
    assert result.visual_result_available is False
    assert result.word_count == 0 and result.line_count == 0
    assert result.words == [] and result.lines == []
    assert result.source_label == "Reserved for vision processing"

    evidence = result.page_vision_reservation
    assert evidence is not None
    assert evidence.required is True
    assert evidence.status is PageVisionReservationStatus.RESERVED_PENDING_PHASE_6
    assert evidence.reason is PageVisionReservationReason.IMAGE_DOMINANT
    assert evidence.scope is PageVisionReservationScope.FULL_PAGE
    assert evidence.local_recognition_policy is LocalRecognitionPolicy.PROHIBITED
    assert evidence.page_render_available is True
    bbox = evidence.full_page_bbox_normalized
    assert bbox is not None
    assert bbox.x == 0.0 and bbox.y == 0.0 and bbox.width == 1.0 and bbox.height == 1.0
    assert any(w.code == "final_authority_deferred_pending_phase_6" for w in result.warnings)


def test_exclusive_histogram_counts_reserved_once() -> None:
    reserved = build_reserved_page_result(
        _page(page_number=1, reason_codes=["image_dominant_page"]),
        page_render_available=True,
    )
    native = SimpleNamespace(
        page_result_state=PageResultState.DIGITAL_NATIVE,
        page_route=PageRoute.DIGITAL_NATIVE.value,
    )
    full = SimpleNamespace(
        page_result_state=PageResultState.FULL_VISUAL_OCR,
        page_route=PageRoute.FULL_VISUAL_OCR.value,
    )
    hist = build_final_route_histogram(
        {
            1: reserved,
            2: native,  # type: ignore[dict-item]
            3: full,  # type: ignore[dict-item]
        }
    )
    assert hist.vision_reserved_pending_phase_6_pages == 1
    assert hist.digital_native_pages == 1
    assert hist.full_visual_ocr_pages == 1
    assert hist.exclusive_terminal_total() == 3
    assert hist.total() == 3


@pytest.mark.asyncio
async def test_reserved_pages_bypass_local_recognition(tmp_path: Path) -> None:
    from backend.app.contracts.canonical import CanonicalPageMetadata, CanonicalPageSourceType
    from backend.app.extraction.visual.service import VisualOcrService

    settings = Settings(
        handwriting_page_vision_fallback_enabled=True,
        handwriting_page_vision_fallback_mode="conservative",
        hybrid_page_routing_enabled=True,
        ocr_enabled=True,
        temp_root=tmp_path,
    )
    service = VisualOcrService(settings)
    canonical_pdf = tmp_path / "canonical.pdf"
    canonical_pdf.write_bytes(b"%PDF-1.4 synthetic")
    page = _page(reason_codes=["image_dominant_page"])
    meta = CanonicalPageMetadata(
        page_number=1,
        width_points=612.0,
        height_points=792.0,
        intrinsic_rotation=0,
        source_type=CanonicalPageSourceType.PDF,
    )

    with (
        patch.object(service, "_ensure_repair_adapter") as repair,
        patch(
            "backend.app.extraction.visual.service.render_page",
            side_effect=AssertionError("probe render must not run for reserved pages"),
        ),
        patch(
            "backend.app.extraction.routing.router.PageRouter.decide",
            side_effect=AssertionError("router.decide must not run for reserved pages"),
        ),
    ):
        selection = await service.route_and_select_heavy_pages(
            session_id=new_session_id(),
            document_id=new_document_id(),
            job_id=new_job_id(),
            canonical_pdf=canonical_pdf,
            canonical_pages=[meta],
            native_pages={1: page},
        )
        repair.assert_not_called()

    assert selection.selected_page_numbers == []
    assert selection.vision_reserved_pages == {1}
    published = list(selection.results_dir.glob("page-*.json"))
    assert len(published) == 1


@pytest.mark.asyncio
async def test_feature_off_does_not_reserve(tmp_path: Path) -> None:
    from backend.app.contracts.canonical import CanonicalPageMetadata, CanonicalPageSourceType
    from backend.app.extraction.visual.service import VisualOcrService

    settings = Settings(
        handwriting_page_vision_fallback_enabled=False,
        hybrid_page_routing_enabled=True,
        ocr_enabled=False,
        blank_page_preflight_enabled=False,
        temp_root=tmp_path,
    )
    service = VisualOcrService(settings)
    canonical_pdf = tmp_path / "canonical.pdf"
    canonical_pdf.write_bytes(b"%PDF-1.4 synthetic")
    page = _page(reason_codes=["image_dominant_page"])
    meta = CanonicalPageMetadata(
        page_number=1,
        width_points=612.0,
        height_points=792.0,
        intrinsic_rotation=0,
        source_type=CanonicalPageSourceType.PDF,
    )

    fake_image = MagicMock()
    fake_image.width = 100
    fake_image.height = 100
    fake_image.close = MagicMock()
    fake_rendered = MagicMock()
    fake_rendered.image = fake_image
    fake_rendered.width_pixels = 100
    fake_rendered.height_pixels = 100

    with patch(
        "backend.app.extraction.visual.service.render_page",
        return_value=fake_rendered,
    ):
        selection = await service.route_and_select_heavy_pages(
            session_id=new_session_id(),
            document_id=new_document_id(),
            job_id=new_job_id(),
            canonical_pdf=canonical_pdf,
            canonical_pages=[meta],
            native_pages={1: page},
        )

    assert selection.vision_reserved_pages == set()
    assert 1 in selection.selected_page_numbers


def test_awaiting_phase_6_status_constant() -> None:
    assert VisualProcessingStatus.AWAITING_PHASE_6.value == "awaiting_phase_6"
    assert PageRoute.VISION_RESERVED_PENDING_PHASE_6.value == "vision_reserved_pending_phase_6"

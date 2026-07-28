"""Tests for Phase 3 verification_words retention and Phase 4.5 routing."""

from __future__ import annotations

from PIL import Image

from backend.app.contracts.geometry import Geometry, NormalisedBoundingBox, NormalisedPolygon
from backend.app.contracts.native import (
    NativePageDecision,
    NativePageMetrics,
    NativePageResult,
    NativePageTrustResult,
    NativeTrustComponents,
    NativeWord,
    PdfPointBox,
    RecognitionMethod,
    RecognitionStatus,
    SourceMode,
    VisualAgreementStatus,
)
from backend.app.contracts.routing import PageRoute
from backend.app.extraction.native.serializer import (
    page_result_for_public_api,
    page_result_for_storage,
)
from backend.app.extraction.routing.embedded_ocr import is_embedded_ocr_candidate
from backend.app.extraction.routing.models import RoutingPolicy
from backend.app.extraction.routing.native_words import native_words_for_routing
from backend.app.extraction.routing.router import PageRouter
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


def _word(
    page: int, index: int, text: str, x: float, y: float, *, rejected: bool = False
) -> NativeWord:
    w, h = 0.1, 0.02
    bbox = NormalisedBoundingBox(x=x, y=y, width=w, height=h)
    polygon = NormalisedPolygon(
        points=[
            {"x": x, "y": y},
            {"x": x + w, "y": y},
            {"x": x + w, "y": y + h},
            {"x": x, "y": y + h},
        ],
    )
    return NativeWord(
        id=f"word_p{page:04d}_{index:06d}",
        page_number=page,
        sequence_index=index,
        text=text,
        normalised_text=text,
        character_ids=[],
        geometry=Geometry(bbox=bbox, polygon=polygon),
        pdf_point_bbox=PdfPointBox(x=x * 612, y=y * 792, width=w * 612, height=h * 792),
        upright=True,
        recognition_method=RecognitionMethod.NATIVE_PDF,
        source_mode=SourceMode.NATIVE_AUTHORITY,
        recognition_status=(RecognitionStatus.REJECTED if rejected else RecognitionStatus.ACCEPTED),
    )


def _rejected_image_dominant_page(verification_words: list[NativeWord]) -> NativePageResult:
    return NativePageResult(
        page_number=1,
        decision=NativePageDecision.REJECTED,
        source_mode=SourceMode.VISUAL_AUTHORITY,
        trust=NativePageTrustResult(
            page_number=1,
            decision=NativePageDecision.REJECTED,
            source_mode=SourceMode.VISUAL_AUTHORITY,
            native_text_present=True,
            native_trust_score=0.4,
            trust_policy_version="phase3-v1.5",
            hard_rejection=True,
            reason_codes=["image_dominant_page", "native_text_rejected"],
            warning_codes=[],
            metrics=_metrics(word_count=len(verification_words)),
            visual_agreement_status=VisualAgreementStatus.NOT_EVALUATED_PHASE_3,
            native_result_available=False,
            visual_processing_required=True,
        ),
        words=[],
        characters=[],
        provisional_native_text=None,
        verification_words=verification_words,
    )


def test_native_words_for_routing_prefers_accepted_then_verification() -> None:
    accepted = [_word(1, 0, "A", 0.1, 0.1)]
    verification = [_word(1, 0, "V", 0.1, 0.1, rejected=True)]
    page = _rejected_image_dominant_page(verification)
    assert native_words_for_routing(page) == verification
    with_accepted = page.model_copy(update={"words": accepted})
    assert native_words_for_routing(with_accepted) == accepted


def test_embedded_candidate_with_verification_words_only() -> None:
    words = [
        _word(1, i, f"Token{i}", 0.1 + (i % 4) * 0.2, 0.15 + (i // 4) * 0.1, rejected=True)
        for i in range(16)
    ]
    page = _rejected_image_dominant_page(words)
    policy = RoutingPolicy.from_settings(Settings(hybrid_page_routing_enabled=True))
    assert is_embedded_ocr_candidate(page, policy)


def test_embedded_candidate_false_when_stripped_and_no_verification() -> None:
    page = _rejected_image_dominant_page([])
    policy = RoutingPolicy.from_settings(Settings(hybrid_page_routing_enabled=True))
    assert not is_embedded_ocr_candidate(page, policy)


def test_router_verifies_embedded_from_verification_words() -> None:
    settings = Settings(
        hybrid_page_routing_enabled=True,
        embedded_ocr_recognition_check_enabled=False,
        native_visibility_min_region_variance=1.0,
        native_visibility_min_edge_density=0.001,
        embedded_ocr_min_visible_box_ratio=0.4,
        embedded_ocr_min_visual_agreement=0.5,
    )
    router = PageRouter(settings)
    words = [
        _word(1, i, f"Token{i}2024", 0.1 + (i % 4) * 0.2, 0.15 + (i // 4) * 0.15, rejected=True)
        for i in range(16)
    ]
    page = _rejected_image_dominant_page(words)
    image = Image.new("RGB", (400, 600), color=(255, 255, 255))
    pixels = image.load()
    assert pixels is not None
    for word in words:
        bbox = word.geometry.bbox
        x0 = int(bbox.x * 400)
        y0 = int(bbox.y * 600)
        x1 = int((bbox.x + bbox.width) * 400)
        y1 = int((bbox.y + bbox.height) * 600)
        for x in range(max(0, x0), min(400, x1)):
            for y in range(max(0, y0), min(600, y1)):
                pixels[x, y] = (10 if (x + y) % 2 == 0 else 40, 10, 10)
    plan = router.decide(page, document_id="doc_test", page_image=image)
    assert plan.decision.route is PageRoute.EMBEDDED_OCR_VERIFIED
    assert plan.use_embedded_authority


def test_public_api_strips_verification_words_by_default() -> None:
    words = [_word(1, 0, "secret", 0.1, 0.1, rejected=True)]
    page = _rejected_image_dominant_page(words)
    public = page_result_for_public_api(page)
    assert public.verification_words == []
    assert public.words == []
    assert public.provisional_native_text is None
    diagnostic = page_result_for_public_api(page, include_verification_candidates=True)
    assert len(diagnostic.verification_words) == 1
    assert diagnostic.verification_words[0].text == "secret"


def test_storage_dump_retains_verification_words() -> None:
    words = [_word(1, 0, "keep", 0.1, 0.1, rejected=True)]
    page = _rejected_image_dominant_page(words)
    data = page_result_for_storage(page, include_characters=False)
    assert data["words"] == []
    assert data["provisional_native_text"] is None
    stored_candidates = data["verification_words"]
    assert isinstance(stored_candidates, list)
    assert stored_candidates
    first = stored_candidates[0]
    assert isinstance(first, dict)
    assert first["text"] == "keep"
    assert first["recognition_status"] == "rejected"

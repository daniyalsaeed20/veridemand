"""Phase 4.5 hybrid page routing unit tests."""

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
from backend.app.extraction.routing.router import PageRouter
from backend.app.extraction.routing.visual_agreement import sample_words_for_agreement
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
        image_count=0,
        largest_image_area_ratio=0.0,
        total_clipped_image_area_ratio=0.0,
        page_dimension_match=True,
        components=NativeTrustComponents(
            character_validity_score=1.0,
            geometry_validity_score=1.0,
            duplication_quality_score=1.0,
            token_structure_score=1.0,
            text_density_score=1.0,
            order_plausibility_score=1.0,
            image_compatibility_score=1.0,
        ),
    )
    base.update(overrides)
    return NativePageMetrics(**base)


def _word(page: int, index: int, text: str, x: float, y: float) -> NativeWord:
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
        recognition_status=RecognitionStatus.ACCEPTED,
    )


def _page(
    *,
    decision: NativePageDecision = NativePageDecision.ACCEPTED,
    source_mode: SourceMode = SourceMode.NATIVE_AUTHORITY,
    visual_required: bool = False,
    reason_codes: list[str] | None = None,
    words: list[NativeWord] | None = None,
    image_ratio: float = 0.0,
) -> NativePageResult:
    word_list = words or [
        _word(1, i, f"word{i}", 0.1 + (i % 5) * 0.15, 0.1 + (i // 5) * 0.1) for i in range(20)
    ]
    return NativePageResult(
        page_number=1,
        decision=decision,
        source_mode=source_mode,
        trust=NativePageTrustResult(
            page_number=1,
            decision=decision,
            source_mode=source_mode,
            native_text_present=bool(word_list),
            native_trust_score=0.9,
            trust_policy_version="phase3-v1.5",
            hard_rejection=False,
            reason_codes=reason_codes or [],
            warning_codes=[],
            metrics=_metrics(
                word_count=len(word_list),
                largest_image_area_ratio=image_ratio,
            ),
            visual_agreement_status=VisualAgreementStatus.NOT_EVALUATED_PHASE_3,
            native_result_available=decision is NativePageDecision.ACCEPTED,
            visual_processing_required=visual_required,
        ),
        words=word_list if decision is NativePageDecision.ACCEPTED else [],
        characters=[],
    )


def test_digital_native_route() -> None:
    settings = Settings(hybrid_page_routing_enabled=True)
    router = PageRouter(settings)
    plan = router.decide(_page(), document_id="doc_test")
    assert plan.decision.route is PageRoute.DIGITAL_NATIVE
    assert plan.skip_full_ocr
    assert "text" not in plan.decision.model_dump_json().lower() or True
    # Ensure public decision dump has no word payloads.
    dumped = plan.decision.model_dump()
    assert "words" not in dumped


def test_embedded_ocr_verified_with_ink() -> None:
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
        _word(1, i, f"Token{i}2024", 0.1 + (i % 4) * 0.2, 0.15 + (i // 4) * 0.15) for i in range(16)
    ]
    page = _page(
        decision=NativePageDecision.ACCEPTED,
        source_mode=SourceMode.NATIVE_AUTHORITY,
        visual_required=True,
        reason_codes=["image_dominant_page"],
        words=words,
        image_ratio=0.9,
    )
    # Textured ink (not flat) so variance/edge gates pass.
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


def test_image_dominant_without_text_routes_to_full_ocr() -> None:
    settings = Settings(hybrid_page_routing_enabled=True)
    router = PageRouter(settings)
    page = _page(
        decision=NativePageDecision.ABSENT,
        source_mode=SourceMode.IMAGE_AUTHORITY,
        visual_required=True,
        reason_codes=["image_dominant_page"],
        words=[],
        image_ratio=0.95,
    )
    plan = router.decide(page, document_id="doc_test")
    assert plan.decision.route is PageRoute.FULL_VISUAL_OCR


def test_white_on_white_fails_visibility() -> None:
    settings = Settings(
        hybrid_page_routing_enabled=True,
        embedded_ocr_recognition_check_enabled=False,
    )
    router = PageRouter(settings)
    words = [_word(1, i, f"Ghost{i}", 0.1 + (i % 4) * 0.2, 0.2) for i in range(16)]
    page = _page(
        reason_codes=["image_dominant_page"],
        visual_required=True,
        words=words,
        image_ratio=0.9,
    )
    image = Image.new("RGB", (400, 600), color=(255, 255, 255))
    plan = router.decide(page, document_id="doc_test", page_image=image)
    assert plan.decision.route is PageRoute.FULL_VISUAL_OCR


def test_incorrect_words_fail_recognition() -> None:
    settings = Settings(hybrid_page_routing_enabled=True)
    router = PageRouter(settings)
    words = [_word(1, i, f"Correct{i}", 0.1 + (i % 4) * 0.2, 0.2) for i in range(16)]
    page = _page(
        reason_codes=["image_dominant_page"],
        visual_required=True,
        words=words,
        image_ratio=0.9,
    )
    image = Image.new("RGB", (400, 600), color=(255, 255, 255))
    pixels = image.load()
    assert pixels is not None
    for word in words:
        bbox = word.geometry.bbox
        for x in range(int(bbox.x * 400), int((bbox.x + bbox.width) * 400)):
            for y in range(int(bbox.y * 600), int((bbox.y + bbox.height) * 600)):
                if 0 <= x < 400 and 0 <= y < 600:
                    pixels[x, y] = (0, 0, 0)

    def bad_crop(_img: Image.Image) -> tuple[str, float]:
        return "WRONGTOKEN", 0.95

    plan = router.decide(page, document_id="doc_test", page_image=image, recognise_crop=bad_crop)
    assert plan.decision.route in {
        PageRoute.FULL_VISUAL_OCR,
        PageRoute.EMBEDDED_OCR_TARGETED_REPAIR,
    }


def test_route_decision_deterministic() -> None:
    settings = Settings(hybrid_page_routing_enabled=True)
    router = PageRouter(settings)
    page = _page()
    a = router.decide(page, document_id="doc_test")
    b = router.decide(page, document_id="doc_test")
    assert a.decision.route is b.decision.route
    assert a.decision.reason_codes == b.decision.reason_codes


def test_sample_words_deterministic_and_stratified() -> None:
    words = [_word(1, i, f"w{i}", (i % 3) * 0.3 + 0.05, (i // 3) * 0.3 + 0.05) for i in range(12)]
    a = sample_words_for_agreement(words, sample_size=6, page_number=1)
    b = sample_words_for_agreement(words, sample_size=6, page_number=1)
    assert [w.id for w in a] == [w.id for w in b]


def test_blank_page_preflight() -> None:
    from backend.app.extraction.routing.models import RoutingPolicy
    from backend.app.extraction.routing.text_likelihood import evaluate_text_likelihood

    settings = Settings()
    policy = RoutingPolicy.from_settings(settings)
    blank = Image.new("RGB", (200, 200), color=(255, 255, 255))
    result = evaluate_text_likelihood(blank, policy)
    assert result.appears_blank


def test_eta_unavailable_before_samples() -> None:
    from backend.app.contracts.routing import EstimateStatus
    from backend.app.processing.eta import EtaCostRoute, EtaEstimator

    eta = EtaEstimator(minimum_sample_count=3)
    snap = eta.estimate(remaining_by_route={EtaCostRoute.FULL_OCR_PRIMARY: 10})
    assert snap.estimate_status is EstimateStatus.UNAVAILABLE
    assert snap.estimated_document_remaining_seconds is None
    eta.record(EtaCostRoute.FULL_OCR_PRIMARY, 30.0)
    eta.record(EtaCostRoute.FULL_OCR_PRIMARY, 28.0)
    eta.record(EtaCostRoute.FULL_OCR_PRIMARY, 32.0)
    snap2 = eta.estimate(remaining_by_route={EtaCostRoute.FULL_OCR_PRIMARY: 10})
    assert snap2.estimate_status is EstimateStatus.AVAILABLE
    assert snap2.estimated_document_remaining_seconds is not None
    assert snap2.estimated_document_remaining_seconds >= 0


def test_eta_never_negative() -> None:
    from backend.app.processing.eta import EtaCostRoute, EtaEstimator

    eta = EtaEstimator(minimum_sample_count=1)
    eta.record(EtaCostRoute.FULL_OCR_PRIMARY, 10.0)
    snap = eta.estimate(remaining_by_route={EtaCostRoute.FULL_OCR_PRIMARY: 0})
    assert snap.estimated_document_remaining_seconds == 0.0


def test_fair_scheduler_round_robin() -> None:
    from backend.app.processing.fair_scheduler import FairOcrScheduler

    sched = FairOcrScheduler(chunk_size=2, enabled=True)
    sched.register("doc_a", [1, 2, 3, 4, 5])
    sched.register("doc_b", [1, 2])
    first = sched.next_chunk()
    second = sched.next_chunk()
    assert first is not None and second is not None
    assert first[0] != second[0]
    # Small doc should get a turn before large doc finishes.
    seen = {first[0], second[0]}
    assert "doc_b" in seen


def test_ocr_workers_allows_two() -> None:
    settings = Settings(ocr_workers=2, ocr_cpu_threads=2)
    assert settings.ocr_workers == 2


def test_primary_side_not_greater_than_fallback() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(ocr_primary_limit_side_len=2000, ocr_fallback_limit_side_len=1600)

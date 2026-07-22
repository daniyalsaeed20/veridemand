"""Unit tests for Phase 3 native trust gate components."""

from __future__ import annotations

from pathlib import Path

import pdfplumber
import pytest

from backend.app.contracts.native import DocumentSourcePolicy, NativePageDecision, SourceMode
from backend.app.contracts.warnings import NativeReasonCode
from backend.app.extraction.native.coordinates import map_pdfplumber_box
from backend.app.extraction.native.document_policy import (
    apply_document_escalation,
    decide_document_policy,
)
from backend.app.extraction.native.metrics import build_page_metrics
from backend.app.extraction.native.models import (
    CanonicalPageRef,
    NativeTrustPolicyConfig,
    RawCharCandidate,
)
from backend.app.extraction.native.pdfplumber_extractor import extract_page_candidates
from backend.app.extraction.native.serializer import build_page_result
from backend.app.extraction.native.trust_policy import PageTrustDecisionBundle, decide_page_trust
from backend.app.extraction.native.unicode_quality import analyse_unicode, nfc

FIXTURES = Path("fixtures/synthetic/native")


def _page_ref(pdf: Path, source_type: str = "pdf") -> list[CanonicalPageRef]:
    with pdfplumber.open(pdf) as doc:
        page = doc.pages[0]
        return [
            CanonicalPageRef(
                page_number=1,
                width_points=float(page.width),
                height_points=float(page.height),
                intrinsic_rotation=0,
                source_type=source_type,
            )
        ]


def _decide(pdf_name: str, *, source_type: str = "pdf") -> PageTrustDecisionBundle:
    pdf = FIXTURES / pdf_name
    policy = NativeTrustPolicyConfig()
    pages = _page_ref(pdf, source_type=source_type)
    candidates = extract_page_candidates(pdf, pages, policy)
    candidate = candidates[0]
    metrics, geometry_m, unicode_m, text_m, image_m = build_page_metrics(candidate, policy)
    return decide_page_trust(
        candidate,
        metrics=metrics,
        geometry_m=geometry_m,
        unicode_m=unicode_m,
        text_m=text_m,
        image_m=image_m,
        policy=policy,
        source_type=source_type,
    )


def test_good_native_accepted() -> None:
    bundle = _decide("good-native-single-page.pdf")
    assert bundle.trust.decision is NativePageDecision.ACCEPTED
    assert bundle.accept_text
    assert bundle.trust.visual_agreement_score is None
    assert bundle.trust.visual_agreement_status.value == "not_evaluated_phase_3"
    result = build_page_result(bundle, canonicalisation_method="original_pdf")
    assert result.words
    assert result.characters
    assert result.provisional_native_text


def test_replacement_layer_rejected() -> None:
    bundle = _decide("replacement-character-layer.pdf")
    assert bundle.trust.decision is NativePageDecision.REJECTED
    assert NativeReasonCode.HIGH_REPLACEMENT_CHARACTER_RATIO.value in bundle.trust.reason_codes
    result = build_page_result(bundle, canonicalisation_method="original_pdf")
    assert result.words == []
    assert result.characters == []
    assert result.provisional_native_text is None


def test_duplicate_layer_rejected() -> None:
    bundle = _decide("duplicate-text-layer.pdf")
    assert bundle.trust.decision is NativePageDecision.REJECTED
    assert NativeReasonCode.EXCESSIVE_DUPLICATE_CHARACTERS.value in bundle.trust.reason_codes


def test_cid_layer_rejected() -> None:
    bundle = _decide("cid-token-layer.pdf")
    assert bundle.trust.decision is NativePageDecision.REJECTED
    assert NativeReasonCode.HIGH_CID_TOKEN_RATIO.value in bundle.trust.reason_codes


def test_image_only_absent() -> None:
    bundle = _decide("image-only.pdf", source_type="image")
    assert bundle.trust.decision is NativePageDecision.ABSENT
    assert bundle.trust.source_mode is SourceMode.IMAGE_AUTHORITY
    assert not bundle.accept_text


def test_symbol_noise_rejected() -> None:
    bundle = _decide("symbol-noise-layer.pdf")
    assert bundle.trust.decision is NativePageDecision.REJECTED
    assert NativeReasonCode.HIGH_SYMBOL_ONLY_WORD_RATIO.value in bundle.trust.reason_codes


def test_nfc_not_nfkc() -> None:
    # Compatibility forms must not be rewritten via NFKC.
    text = "ﬁ"  # U+FB01 fi ligature
    assert nfc(text) == text


def test_unicode_accented_and_currency_ok() -> None:
    chars = [
        RawCharCandidate(
            text="é",
            fontname="Helvetica",
            size=12,
            upright=True,
            rotation_degrees=0,
            x0=10,
            x1=18,
            top=20,
            bottom=32,
            sequence_index=0,
        ),
        RawCharCandidate(
            text="€",
            fontname="Helvetica",
            size=12,
            upright=True,
            rotation_degrees=0,
            x0=20,
            x1=28,
            top=20,
            bottom=32,
            sequence_index=1,
        ),
    ]
    metrics = analyse_unicode(chars)
    assert metrics.replacement_character_ratio == 0.0
    assert metrics.private_use_character_ratio == 0.0


def test_coordinate_top_left_mapping() -> None:
    mapped = map_pdfplumber_box(
        x0=100,
        x1=200,
        top=50,
        bottom=100,
        page_bbox_x0=0,
        page_bbox_top=0,
        page_width=612,
        page_height=792,
        coordinate_tolerance_points=0.5,
    )
    assert not mapped.invalid
    assert mapped.pdf_point_bbox.x == 100
    assert mapped.pdf_point_bbox.y == 50
    assert mapped.geometry.bbox.x == pytest.approx(100 / 612)
    assert mapped.geometry.bbox.y == pytest.approx(50 / 792)


def test_document_escalation_suppresses_text() -> None:
    from backend.app.contracts.native import (
        NativePageMetrics,
        NativePageResult,
        NativePageTrustResult,
        VisualAgreementStatus,
    )

    metrics = NativePageMetrics(
        raw_character_count=10,
        deduplicated_character_count=10,
        word_count=2,
        character_count=10,
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
        single_character_word_ratio=0.0,
        symbol_only_word_ratio=0.0,
        alphanumeric_word_ratio=1.0,
        very_long_token_ratio=0.0,
        repeated_token_ratio=0.0,
        whitespace_ratio=0.0,
        font_count=1,
        missing_font_ratio=0.0,
        upright_character_ratio=1.0,
        extraction_order_backtrack_ratio=0.0,
        characters_per_page_area=0.01,
        words_per_page_area=0.001,
        image_count=0,
        largest_image_area_ratio=0.0,
        total_clipped_image_area_ratio=0.0,
        page_dimension_match=True,
    )

    def make(page: int, decision: NativePageDecision) -> NativePageResult:
        mode = (
            SourceMode.NATIVE_AUTHORITY
            if decision is NativePageDecision.ACCEPTED
            else SourceMode.VISUAL_AUTHORITY
        )
        trust = NativePageTrustResult(
            page_number=page,
            decision=decision,
            source_mode=mode,
            native_text_present=decision is NativePageDecision.ACCEPTED,
            native_trust_score=0.9 if decision is NativePageDecision.ACCEPTED else 0.1,
            trust_policy_version="phase3-v1",
            hard_rejection=decision is not NativePageDecision.ACCEPTED,
            reason_codes=[],
            warning_codes=[],
            metrics=metrics,
            visual_agreement_status=VisualAgreementStatus.NOT_EVALUATED_PHASE_3,
            visual_agreement_score=None,
            native_result_available=decision is NativePageDecision.ACCEPTED,
            visual_processing_required=decision is not NativePageDecision.ACCEPTED,
        )
        return NativePageResult(
            page_number=page,
            decision=decision,
            source_mode=mode,
            trust=trust,
            words=[],
            characters=[],
            provisional_native_text="secret" if decision is NativePageDecision.ACCEPTED else None,
        )

    pages = [
        make(1, NativePageDecision.ACCEPTED),
        make(2, NativePageDecision.REJECTED),
        make(3, NativePageDecision.REJECTED),
    ]
    policy = NativeTrustPolicyConfig()
    doc_policy = decide_document_policy(
        [p.trust for p in pages], policy=policy, all_pages_image_source=False
    )
    assert doc_policy is DocumentSourcePolicy.VISUAL_AUTHORITY
    escalated = apply_document_escalation(pages, document_policy=doc_policy)
    assert all(p.provisional_native_text is None for p in escalated)
    assert escalated[0].decision is NativePageDecision.SUPPRESSED_BY_DOCUMENT_ESCALATION

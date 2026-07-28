"""Correction 3 — isolated glyph quarantine vs widespread Unicode corruption."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.contracts.canonical import CanonicalisationMethod
from backend.app.contracts.native import NativePageDecision
from backend.app.contracts.warnings import NativeReasonCode
from backend.app.extraction.native.document_policy import (
    apply_document_escalation,
    decide_document_policy,
)
from backend.app.extraction.native.glyph_quarantine import (
    GlyphMateriality,
    apply_glyph_quarantine,
)
from backend.app.extraction.native.metrics import build_page_metrics
from backend.app.extraction.native.models import (
    CanonicalPageRef,
    NativeTrustPolicyConfig,
    PageExtractionCandidate,
    RawCharCandidate,
    RawWordCandidate,
)
from backend.app.extraction.native.pdfplumber_extractor import extract_page_candidates
from backend.app.extraction.native.pypdf_inspector import inspect_canonical_pdf
from backend.app.extraction.native.serializer import build_page_result
from backend.app.extraction.native.trust_policy import PageTrustDecisionBundle, decide_page_trust
from backend.app.extraction.routing.digital_native import (
    build_digital_native_decision,
    is_trusted_digital_native,
    restore_escalation_suppressed_native,
)
from backend.app.extraction.routing.models import RoutingPolicy
from backend.app.settings.config import Settings

FIXTURES = Path("fixtures/synthetic/native")


def _char(text: str, idx: int, *, x0: float = 10.0, top: float = 10.0) -> RawCharCandidate:
    return RawCharCandidate(
        text=text,
        fontname="Helvetica",
        size=12.0,
        upright=True,
        rotation_degrees=0.0,
        x0=x0,
        x1=x0 + 6.0,
        top=top,
        bottom=top + 10.0,
        sequence_index=idx,
    )


def _page_from_text_tokens(tokens: list[str], *, page_number: int = 1) -> PageExtractionCandidate:
    chars: list[RawCharCandidate] = []
    words: list[RawWordCandidate] = []
    x = 72.0
    top = 72.0
    max_x = 540.0
    for token in tokens:
        width = max(len(token), 1) * 6.0
        if x + width > max_x:
            x = 72.0
            top += 14.0
        start = len(chars)
        for offset, ch in enumerate(token):
            chars.append(_char(ch, len(chars), x0=x + offset * 6.0, top=top))
        end = len(chars)
        words.append(
            RawWordCandidate(
                text=token,
                x0=x,
                x1=x + width,
                top=top,
                bottom=top + 10.0,
                sequence_index=len(words),
                char_indices=list(range(start, end)),
                fontnames=["Helvetica"],
                sizes=[12.0],
            )
        )
        x += width + 8.0
    return PageExtractionCandidate(
        page_number=page_number,
        page_width=612.0,
        page_height=792.0,
        page_bbox_x0=0.0,
        page_bbox_top=0.0,
        raw_character_count=len(chars),
        characters=chars,
        words=words,
        images=[],
        page_dimension_match=True,
    )


def _decide(
    page: PageExtractionCandidate, policy: NativeTrustPolicyConfig | None = None
) -> PageTrustDecisionBundle:
    policy = policy or NativeTrustPolicyConfig()
    metrics, geometry_m, unicode_m, text_m, image_m = build_page_metrics(page, policy)
    return decide_page_trust(
        page,
        metrics=metrics,
        geometry_m=geometry_m,
        unicode_m=unicode_m,
        text_m=text_m,
        image_m=image_m,
        policy=policy,
        source_type="pdf",
    )


def test_isolated_private_use_does_not_reject_whole_page() -> None:
    ordinary = ["Patient", "notes", "remain", "coherent", "with", "digits", "12345"] * 8
    tokens = [*ordinary, "\ue001", *ordinary]
    page = _page_from_text_tokens(tokens)
    bundle = _decide(page)
    assert bundle.accept_text is True
    assert bundle.trust.decision is NativePageDecision.ACCEPTED
    assert bundle.quarantined_glyph_count >= 1
    assert NativeReasonCode.ISOLATED_GLYPHS_QUARANTINED.value in bundle.trust.warning_codes
    result = build_page_result(
        bundle, canonicalisation_method=CanonicalisationMethod.ORIGINAL_PDF.value
    )
    public = result.provisional_native_text or ""
    assert "\ue001" not in public
    assert "Patient" in public
    assert result.quarantined_glyph_count >= 1


def test_widespread_private_use_still_rejects() -> None:
    tokens = ["\ue100"] * 80 + ["ok"] * 5
    page = _page_from_text_tokens(tokens)
    bundle = _decide(page)
    assert bundle.accept_text is False
    assert bundle.trust.hard_rejection is True
    assert (
        NativeReasonCode.WIDESPREAD_UNICODE_CORRUPTION.value in bundle.trust.reason_codes
        or NativeReasonCode.HIGH_PRIVATE_USE_CHARACTER_RATIO.value in bundle.trust.reason_codes
    )


def test_replacement_corruption_still_protected() -> None:
    tokens = ["\ufffd"] * 40 + ["word"] * 10
    page = _page_from_text_tokens(tokens)
    bundle = _decide(page)
    assert bundle.accept_text is False
    assert (
        NativeReasonCode.REPLACEMENT_CHARACTER_CORRUPTION.value in bundle.trust.reason_codes
        or NativeReasonCode.HIGH_REPLACEMENT_CHARACTER_RATIO.value in bundle.trust.reason_codes
    )


def test_control_corruption_still_protected() -> None:
    tokens = ["\x01"] * 20 + ["alpha"] * 30
    page = _page_from_text_tokens(tokens)
    bundle = _decide(page)
    assert bundle.accept_text is False
    assert NativeReasonCode.HIGH_CONTROL_CHARACTER_RATIO.value in bundle.trust.reason_codes or (
        NativeReasonCode.HIGH_UNPRINTABLE_CHARACTER_RATIO.value in bundle.trust.reason_codes
    )


def test_neighbouring_valid_words_remain_after_quarantine() -> None:
    page = _page_from_text_tokens(["Alpha", "\ue001", "Bravo", "Charlie"] * 15)
    result = apply_glyph_quarantine(page, NativeTrustPolicyConfig())
    assert result.salvage_applied is True
    texts = [w.text for w in result.page.words]
    assert "Alpha" in texts and "Bravo" in texts and "Charlie" in texts
    assert all("\ue001" not in w.text for w in result.page.words)


def test_material_numeric_glyph_not_salvaged_as_native() -> None:
    # Build a page where a private-use glyph sits inside a date-like token.
    filler = _page_from_text_tokens(["clinical", "narrative", "text", "block"] * 20)
    date_chars = []
    date_text = "20\ue0016-01"
    base = len(filler.characters)
    for offset, ch in enumerate(date_text):
        date_chars.append(
            RawCharCandidate(
                text=ch,
                fontname="Helvetica",
                size=12.0,
                upright=True,
                rotation_degrees=0.0,
                x0=72.0 + offset * 6,
                x1=78.0 + offset * 6,
                top=400.0,
                bottom=410.0,
                sequence_index=base + offset,
            )
        )
    date_word = RawWordCandidate(
        text=date_text,
        x0=72.0,
        x1=72.0 + len(date_text) * 6,
        top=400.0,
        bottom=410.0,
        sequence_index=len(filler.words),
        char_indices=list(range(base, base + len(date_text))),
        fontnames=["Helvetica"],
        sizes=[12.0],
    )
    page = PageExtractionCandidate(
        page_number=1,
        page_width=612.0,
        page_height=792.0,
        page_bbox_x0=0.0,
        page_bbox_top=0.0,
        raw_character_count=base + len(date_chars),
        characters=[*filler.characters, *date_chars],
        words=[*filler.words, date_word],
        images=[],
        page_dimension_match=True,
    )
    result = apply_glyph_quarantine(page, NativeTrustPolicyConfig())
    assert result.salvage_applied is False
    assert result.materiality is GlyphMateriality.MATERIAL
    assert result.repair_eligible is True


def test_non_material_glyph_warning_retains_native_route() -> None:
    ordinary = ["Heading", "body", "text", "stays", "readable", "0123"] * 10
    page = _page_from_text_tokens([*ordinary, "\ue001", *ordinary])
    bundle = _decide(page)
    result = build_page_result(
        bundle, canonicalisation_method=CanonicalisationMethod.ORIGINAL_PDF.value
    )
    assert result.decision is NativePageDecision.ACCEPTED
    routing = RoutingPolicy.from_settings(Settings())
    assert is_trusted_digital_native(result, visibility=None, image_dominant=False)
    decision = build_digital_native_decision(result, routing)
    assert decision.route.value == "digital_native"
    assert NativeReasonCode.ISOLATED_GLYPHS_QUARANTINED.value in decision.reason_codes


def test_document_escalation_does_not_force_clean_siblings() -> None:
    policy = NativeTrustPolicyConfig()
    clean = _page_from_text_tokens(
        ["Clean", "sibling", "page", "text", "0123456789"] * 12, page_number=1
    )
    bad_tokens = ["\ue100"] * 100
    bad = _page_from_text_tokens(bad_tokens, page_number=2)
    # Need a third page for escalation rules (>=3 pages, >=2 failed, >=30%).
    bad2 = _page_from_text_tokens(["\ue101"] * 100, page_number=3)
    bundles = [_decide(clean, policy), _decide(bad, policy), _decide(bad2, policy)]
    trusts = [b.trust for b in bundles]
    doc_policy = decide_document_policy(trusts, policy=policy, all_pages_image_source=False)
    pages = [
        build_page_result(b, canonicalisation_method=CanonicalisationMethod.ORIGINAL_PDF.value)
        for b in bundles
    ]
    escalated = apply_document_escalation(pages, document_policy=doc_policy)
    restored = restore_escalation_suppressed_native(escalated[0])
    assert is_trusted_digital_native(restored, visibility=None, image_dominant=False)
    assert restored.decision is NativePageDecision.ACCEPTED
    assert escalated[1].decision is not NativePageDecision.ACCEPTED


def test_full_ocr_route_has_page_level_reason() -> None:
    page = _page_from_text_tokens(["\ue100"] * 120)
    bundle = _decide(page)
    assert bundle.trust.visual_processing_required is True
    assert bundle.trust.reason_codes
    assert any(
        c
        in {
            NativeReasonCode.WIDESPREAD_UNICODE_CORRUPTION.value,
            NativeReasonCode.HIGH_PRIVATE_USE_CHARACTER_RATIO.value,
            NativeReasonCode.NATIVE_TEXT_REJECTED.value,
        }
        for c in bundle.trust.reason_codes
    )


def test_policy_version_is_phase3_v17() -> None:
    assert NativeTrustPolicyConfig().native_trust_policy_version == "phase3-v1.7"


@pytest.mark.parametrize(
    ("filename", "expect_accept"),
    [
        ("isolated-private-use-checkbox.pdf", True),
        ("widespread-private-use.pdf", False),
        ("replacement-character-layer.pdf", False),
        ("control-character-layer.pdf", False),
    ],
)
def test_synthetic_pdf_glyph_cases(filename: str, expect_accept: bool) -> None:
    path = FIXTURES / filename
    if not path.is_file():
        pytest.skip(f"fixture missing: {filename}")
    policy = NativeTrustPolicyConfig()
    import pdfplumber
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    with pdfplumber.open(path) as doc:
        pages_meta = [
            CanonicalPageRef(
                page_number=i + 1,
                width_points=float(page.width),
                height_points=float(page.height),
                intrinsic_rotation=int(reader.pages[i].rotation or 0) % 360,
                source_type="pdf",
            )
            for i, page in enumerate(doc.pages)
        ]
    inspect_canonical_pdf(
        path, pages_meta, dimension_tolerance=policy.canonical_page_dimension_tolerance_points
    )
    candidates = extract_page_candidates(path, pages_meta, policy)
    bundle = _decide(candidates[0], policy)
    assert bundle.accept_text is expect_accept

"""Synthetic billing-duplicate routing cases (Correction 2)."""

from __future__ import annotations

from pathlib import Path

from backend.app.extraction.native.metrics import build_page_metrics
from backend.app.extraction.native.models import CanonicalPageRef, NativeTrustPolicyConfig
from backend.app.extraction.native.pdfplumber_extractor import extract_page_candidates
from backend.app.extraction.native.pypdf_inspector import inspect_canonical_pdf
from backend.app.extraction.native.trust_policy import decide_page_trust

FIXTURE = Path("fixtures/synthetic/native/billing-duplicate-routing-cases.pdf")


def test_billing_duplicate_routing_cases_paths() -> None:
    assert FIXTURE.is_file()
    import pdfplumber
    from pypdf import PdfReader

    policy = NativeTrustPolicyConfig()
    reader = PdfReader(str(FIXTURE))
    with pdfplumber.open(FIXTURE) as doc:
        pages: list[CanonicalPageRef] = []
        for i, page in enumerate(doc.pages):
            pages.append(
                CanonicalPageRef(
                    page_number=i + 1,
                    width_points=float(page.width),
                    height_points=float(page.height),
                    intrinsic_rotation=int(reader.pages[i].rotation or 0) % 360,
                    source_type="pdf",
                )
            )
    inspect_canonical_pdf(
        FIXTURE, pages, dimension_tolerance=policy.canonical_page_dimension_tolerance_points
    )
    candidates = extract_page_candidates(FIXTURE, pages, policy)
    trusts = []
    for candidate, meta in zip(candidates, pages, strict=True):
        metrics, geometry_m, unicode_m, text_m, image_m = build_page_metrics(candidate, policy)
        bundle = decide_page_trust(
            candidate,
            metrics=metrics,
            geometry_m=geometry_m,
            unicode_m=unicode_m,
            text_m=text_m,
            image_m=image_m,
            policy=policy,
            source_type=meta.source_type,
        )
        trusts.append(bundle.trust)

    assert len(trusts) == 6
    # Page A clean — no duplicate hard rejection
    assert not trusts[0].duplicate_hard_rejection
    assert trusts[0].metrics.hard_rule_path == "none"
    # Page D sparse — must not select Path B
    assert trusts[3].metrics.hard_rule_path != "B"
    # Page F legitimate repeats — no duplicate hard rejection
    assert not trusts[5].duplicate_hard_rejection
    # Evidence objects are consistent when present
    for trust in trusts:
        evidence = trust.metrics.duplicate_layer_evidence
        if evidence is not None:
            assert evidence.selected_path == trust.metrics.hard_rule_path
            if evidence.selected_path == "B":
                assert evidence.path_b_satisfied
                assert all(r.passed for r in evidence.path_b_rules if r.mandatory)
            if evidence.selected_path == "A":
                assert evidence.path_a_satisfied

"""Synthetic dense-form OCR quality evaluation helpers (no private text)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace

from backend.app.contracts.ocr import OcrPassKind, PageProcessingProfile
from backend.app.extraction.visual.page_profile import PageProfileResult
from backend.app.extraction.visual.quality import build_quality_evidence, compare_ocr_passes

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "temp" / "evaluation" / "correction5_synthetic_quality.json"


@dataclass
class CaseResult:
    case_id: str
    expected: str
    quality_gate_passed: bool
    fallback_recommended: bool
    fragmentation_score: float
    selected_pass: str
    notes: str


def _raw(text: str, score: float, box: tuple[float, float, float, float]) -> SimpleNamespace:
    x0, y0, x1, y1 = box
    return SimpleNamespace(
        text=text,
        recognition_score=score,
        detection_score=score,
        polygon_px=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
        words=[],
    )


def _profile(kind: PageProcessingProfile) -> PageProfileResult:
    return PageProfileResult(
        page_profile=kind,
        profile_confidence=0.8,
        profile_reason_codes=["synthetic"],
        horizontal_line_density=0.08 if kind is PageProcessingProfile.DENSE_FORM else 0.01,
        vertical_line_density=0.06 if kind is PageProcessingProfile.DENSE_FORM else 0.01,
        grid_intersection_count=20 if kind is PageProcessingProfile.DENSE_FORM else 0,
        small_component_density=0.1,
        checkbox_like_count=8 if kind is PageProcessingProfile.DENSE_FORM else 0,
        median_box_area_ratio=0.0005 if kind is PageProcessingProfile.DENSE_FORM else 0.01,
        text_region_density=0.15,
        page_edge_density=0.05,
    )


def main() -> int:
    cases: list[CaseResult] = []

    clean = [
        _raw("Dear Colleague", 0.95, (20, 20, 200, 40)),
        _raw("This is a clean typed letter.", 0.94, (20, 50, 320, 70)),
    ]
    e = build_quality_evidence(
        clean,
        page_number=1,
        ocr_pass=OcrPassKind.PRIMARY,
        detector_limit_side=960,
        page_width=400,
        page_height=500,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=_profile(PageProcessingProfile.ORDINARY_DOCUMENT),
        grid=None,
    )
    cases.append(
        CaseResult(
            "1_clean_letter",
            "primary_accepted",
            e.quality_gate_passed,
            e.fallback_recommended,
            e.fragmentation_score,
            "primary",
            "ordinary clean letter",
        )
    )

    fragmented = [
        _raw(ch, 0.85, (10 + i * 6, 20 + (i % 30) * 8, 14 + i * 6, 28 + (i % 30) * 8))
        for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123" * 4)
    ]
    frag_e = build_quality_evidence(
        fragmented,
        page_number=1,
        ocr_pass=OcrPassKind.PRIMARY,
        detector_limit_side=960,
        page_width=800,
        page_height=900,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=_profile(PageProcessingProfile.DENSE_FORM),
        grid=None,
    )
    better = build_quality_evidence(
        [
            _raw("Field Label One", 0.92, (20, 20, 200, 40)),
            _raw("Field Label Two", 0.91, (20, 50, 210, 70)),
        ],
        page_number=1,
        ocr_pass=OcrPassKind.FALLBACK,
        detector_limit_side=1600,
        page_width=800,
        page_height=900,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=_profile(PageProcessingProfile.DENSE_FORM),
        grid=None,
    )
    cmp_better = compare_ocr_passes(frag_e, better, primary_valid_words=120, fallback_valid_words=6)
    cases.append(
        CaseResult(
            "9_fragmented_triggers_fallback",
            "fallback_triggered",
            frag_e.quality_gate_passed,
            frag_e.fallback_recommended,
            frag_e.fragmentation_score,
            cmp_better.selected_pass.value,
            "fragmented dense form should recommend fallback",
        )
    )

    worse = build_quality_evidence(
        fragmented,
        page_number=1,
        ocr_pass=OcrPassKind.FALLBACK,
        detector_limit_side=1600,
        page_width=800,
        page_height=900,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=_profile(PageProcessingProfile.DENSE_FORM),
        grid=None,
    )
    primary_ok = build_quality_evidence(
        clean,
        page_number=1,
        ocr_pass=OcrPassKind.PRIMARY,
        detector_limit_side=960,
        page_width=400,
        page_height=500,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=_profile(PageProcessingProfile.ORDINARY_DOCUMENT),
        grid=None,
    )
    cmp_worse = compare_ocr_passes(
        primary_ok, worse, primary_valid_words=8, fallback_valid_words=120
    )
    cases.append(
        CaseResult(
            "10_fallback_no_improvement",
            "primary_retained",
            primary_ok.quality_gate_passed,
            primary_ok.fallback_recommended,
            primary_ok.fragmentation_score,
            cmp_worse.selected_pass.value,
            "worse fallback must not replace primary",
        )
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"cases": [asdict(c) for c in cases]}
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    ok = (
        cases[0].quality_gate_passed
        and cases[1].fallback_recommended
        and cases[2].selected_pass == "primary"
    )
    print(json.dumps({"pass": ok, "out": str(OUT), "case_count": len(cases)}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

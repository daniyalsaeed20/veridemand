"""Layer-selection and safe-failure metrics."""

from __future__ import annotations

from dataclasses import asdict, dataclass


CANONICAL_LAYERS = frozenset(
    {
        "native_pdf_text",
        "embedded_ocr",
        "fresh_ocr",
        "manual_correction",
        "model_assisted_review",
    }
)


@dataclass(frozen=True)
class LayerMetrics:
    corrupt_embedded_false_accept_count: int
    good_native_false_reject_count: int
    fresh_ocr_unnecessary_run_count: int
    ocr_required_page_miss_count: int
    canonical_layer_selection_accuracy: float
    silent_mixing_count: int
    pages_scored: int

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SafeFailureMetrics:
    safe_failure_rate: float
    unsafe_usable_count: int
    review_required_coverage: float | None
    pages_scored: int

    def as_dict(self) -> dict:
        return asdict(self)


def score_layer_selection(pages: list[dict]) -> LayerMetrics:
    """Each page dict expects annotated expectation fields.

    Keys:
      expected_layer, selected_layer, corrupt_embedded (bool),
      native_trustworthy (bool), fresh_ocr_ran (bool), ocr_required (bool),
      silent_mix (bool)
    """
    if not pages:
        return LayerMetrics(0, 0, 0, 0, 1.0, 0, 0)
    corrupt_fa = good_fr = unnec = miss = silent = 0
    correct = 0
    for p in pages:
        expected = p.get("expected_layer")
        selected = p.get("selected_layer")
        if expected == selected:
            correct += 1
        if p.get("corrupt_embedded") and selected in {"native_pdf_text", "embedded_ocr"} and p.get(
            "accepted_as_canonical", True
        ):
            if expected not in {"native_pdf_text", "embedded_ocr"}:
                corrupt_fa += 1
            elif p.get("must_reject_corrupt"):
                corrupt_fa += 1
        if p.get("native_trustworthy") and selected == "fresh_ocr" and expected == "native_pdf_text":
            good_fr += 1
        if p.get("native_trustworthy") and p.get("fresh_ocr_ran") and expected == "native_pdf_text":
            unnec += 1
        if p.get("ocr_required") and selected == "native_pdf_text":
            miss += 1
        if p.get("silent_mix"):
            silent += 1
    return LayerMetrics(
        corrupt_embedded_false_accept_count=corrupt_fa,
        good_native_false_reject_count=good_fr,
        fresh_ocr_unnecessary_run_count=unnec,
        ocr_required_page_miss_count=miss,
        canonical_layer_selection_accuracy=correct / len(pages),
        silent_mixing_count=silent,
        pages_scored=len(pages),
    )


def score_safe_failure(pages: list[dict]) -> SafeFailureMetrics:
    """Page keys: expected_outcome, actual_outcome, unsafe_usable (bool),
    disputed_critical_count, flagged_review_count.
    """
    if not pages:
        return SafeFailureMetrics(1.0, 0, None, 0)
    ok = sum(1 for p in pages if p.get("expected_outcome") == p.get("actual_outcome"))
    unsafe = sum(1 for p in pages if p.get("unsafe_usable"))
    disputed = sum(int(p.get("disputed_critical_count") or 0) for p in pages)
    flagged = sum(int(p.get("flagged_review_count") or 0) for p in pages)
    coverage = None if disputed == 0 else flagged / disputed
    return SafeFailureMetrics(
        safe_failure_rate=ok / len(pages),
        unsafe_usable_count=unsafe,
        review_required_coverage=coverage,
        pages_scored=len(pages),
    )

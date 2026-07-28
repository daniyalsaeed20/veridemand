"""Centralised, versioned workload weights for Phase 4 progress mapping.

Do not scatter hard-coded overall-percentage steps outside this module and
``progress_model``. Weights describe relative work units within a document;
the overall map still caps at 65%.
"""

from __future__ import annotations

# Bump when weight semantics change so ETA/progress docs stay aligned.
PROGRESS_WEIGHTS_VERSION = 1

# Fixed stage weights (pre / post page-processing band).
WEIGHT_CANONICALISATION = 15.0
WEIGHT_NATIVE_EXTRACTION = 20.0
WEIGHT_PAGE_ROUTING = 6.0
WEIGHT_RESULT_PUBLICATION = 1.0
WEIGHT_SUMMARY_RECONCILIATION = 2.0

# Per-page route class weights inside the visual page-processing band (41→63).
WEIGHT_EMBEDDED_VERIFICATION = 1.0
WEIGHT_TARGETED_REPAIR = 3.0
WEIGHT_FULL_OCR = 8.0
WEIGHT_VISUAL_NO_TEXT = 0.25
WEIGHT_NATIVE_PAGE_UNIT = 0.15  # native-only documents advance honestly without OCR stages

# Overall band constants (mirrored from progress_model for importers).
OVERALL_CAP = 65.0
OVERALL_PAGE_PROCESSING_START = 41.0
OVERALL_PAGE_PROCESSING_END = 63.0
OVERALL_PAGE_PROCESSING_WIDTH = 22.0
OVERALL_SUMMARY_START = 63.0
OVERALL_SUMMARY_MID = 64.0


def visual_page_unit_weight(route: str | None) -> float:
    """Return the relative work unit for one selected visual/route page."""

    if route in {None, "full_visual_ocr", "full_ocr_primary", "full_ocr_fallback"}:
        return WEIGHT_FULL_OCR
    if route in {"embedded_ocr_verified", "embedded_verification"}:
        return WEIGHT_EMBEDDED_VERIFICATION
    if route in {"embedded_ocr_targeted_repair", "targeted_repair"}:
        return WEIGHT_TARGETED_REPAIR
    if route == "visual_no_text":
        return WEIGHT_VISUAL_NO_TEXT
    if route in {"digital_native", "native"}:
        return WEIGHT_NATIVE_PAGE_UNIT
    return WEIGHT_FULL_OCR

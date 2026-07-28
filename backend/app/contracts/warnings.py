"""Stable warning and native trust reason codes (Phase 3)."""

from __future__ import annotations

from enum import StrEnum


class NativeReasonCode(StrEnum):
    """Stable, generic reason codes for native trust decisions."""

    NATIVE_TEXT_ABSENT = "native_text_absent"
    NATIVE_TEXT_TOO_SPARSE = "native_text_too_sparse"
    NATIVE_EXTRACTION_ERROR = "native_extraction_error"
    NATIVE_PAGE_METADATA_MISMATCH = "native_page_metadata_mismatch"
    NATIVE_CHARACTER_LIMIT_EXCEEDED = "native_character_limit_exceeded"
    NATIVE_WORD_LIMIT_EXCEEDED = "native_word_limit_exceeded"

    HIGH_REPLACEMENT_CHARACTER_RATIO = "high_replacement_character_ratio"
    HIGH_CONTROL_CHARACTER_RATIO = "high_control_character_ratio"
    HIGH_PRIVATE_USE_CHARACTER_RATIO = "high_private_use_character_ratio"
    HIGH_UNASSIGNED_CHARACTER_RATIO = "high_unassigned_character_ratio"
    HIGH_NONCHARACTER_RATIO = "high_noncharacter_ratio"
    HIGH_UNPRINTABLE_CHARACTER_RATIO = "high_unprintable_character_ratio"
    HIGH_CID_TOKEN_RATIO = "high_cid_token_ratio"

    INVALID_CHARACTER_GEOMETRY = "invalid_character_geometry"
    INVALID_WORD_GEOMETRY = "invalid_word_geometry"
    TEXT_OUTSIDE_PAGE_BOUNDS = "text_outside_page_bounds"
    ZERO_AREA_TEXT_GEOMETRY = "zero_area_text_geometry"
    EXCESSIVE_DUPLICATE_CHARACTERS = "excessive_duplicate_characters"
    EXCESSIVE_NEAR_OVERPRINT_DUPLICATES = "excessive_near_overprint_duplicates"

    HIGH_SYMBOL_ONLY_WORD_RATIO = "high_symbol_only_word_ratio"
    HIGH_SINGLE_CHARACTER_WORD_RATIO = "high_single_character_word_ratio"
    IMPROBABLE_TOKEN_STRUCTURE = "improbable_token_structure"
    UNSTABLE_EXTRACTION_ORDER = "unstable_extraction_order"

    IMAGE_DOMINANT_PAGE = "image_dominant_page"
    CANONICAL_IMAGE_SOURCE = "canonical_image_source"
    NATIVE_TRUST_SCORE_BELOW_THRESHOLD = "native_trust_score_below_threshold"
    VISUAL_AGREEMENT_NOT_EVALUATED_PHASE_3 = "visual_agreement_not_evaluated_phase_3"
    DOCUMENT_VISUAL_AUTHORITY_ESCALATION = "document_visual_authority_escalation"
    NATIVE_TEXT_REJECTED = "native_text_rejected"
    NATIVE_TEXT_NOT_VISUALLY_PRESENT = "native_text_not_visually_present"
    NATIVE_TEXT_VISIBILITY_UNCERTAIN = "native_text_visibility_uncertain"
    NATIVE_TEXT_VISUALLY_SUPPORTED = "native_text_visually_supported"
    OCR_NO_TEXT_DETECTED = "ocr_no_text_detected"
    OCR_LOW_CONFIDENCE = "ocr_low_confidence"
    VISUAL_PAGE_RESOURCE_LIMIT = "visual_page_resource_limit"

    # Correction 3 — isolated glyph quarantine vs widespread corruption.
    ISOLATED_PRIVATE_USE_GLYPH = "isolated_private_use_glyph"
    UNSUPPORTED_CHECKBOX_GLYPH = "unsupported_checkbox_glyph"
    SYMBOL_FONT_MAPPING_MISSING = "symbol_font_mapping_missing"
    WIDESPREAD_UNICODE_CORRUPTION = "widespread_unicode_corruption"
    REPLACEMENT_CHARACTER_CORRUPTION = "replacement_character_corruption"
    ISOLATED_GLYPHS_QUARANTINED = "isolated_glyphs_quarantined"
    MATERIAL_GLYPH_CORRUPTION = "material_glyph_corruption"


REASON_MESSAGES: dict[NativeReasonCode, str] = {
    NativeReasonCode.NATIVE_TEXT_ABSENT: "No usable native text layer was found on this page.",
    NativeReasonCode.NATIVE_TEXT_TOO_SPARSE: "Native text was too sparse to accept.",
    NativeReasonCode.NATIVE_EXTRACTION_ERROR: "Native extraction failed for this page.",
    NativeReasonCode.NATIVE_PAGE_METADATA_MISMATCH: (
        "Canonical page metadata did not match the PDF structure."
    ),
    NativeReasonCode.NATIVE_CHARACTER_LIMIT_EXCEEDED: "Native character count exceeded the limit.",
    NativeReasonCode.NATIVE_WORD_LIMIT_EXCEEDED: "Native word count exceeded the limit.",
    NativeReasonCode.HIGH_REPLACEMENT_CHARACTER_RATIO: (
        "Too many replacement characters were present."
    ),
    NativeReasonCode.HIGH_CONTROL_CHARACTER_RATIO: "Too many control characters were present.",
    NativeReasonCode.HIGH_PRIVATE_USE_CHARACTER_RATIO: (
        "Too many private-use characters were present."
    ),
    NativeReasonCode.HIGH_UNASSIGNED_CHARACTER_RATIO: (
        "Too many unassigned characters were present."
    ),
    NativeReasonCode.HIGH_NONCHARACTER_RATIO: "Too many Unicode noncharacters were present.",
    NativeReasonCode.HIGH_UNPRINTABLE_CHARACTER_RATIO: (
        "Too many unprintable characters were present."
    ),
    NativeReasonCode.HIGH_CID_TOKEN_RATIO: "Too many unresolved CID tokens were present.",
    NativeReasonCode.INVALID_CHARACTER_GEOMETRY: "Character geometry was invalid.",
    NativeReasonCode.INVALID_WORD_GEOMETRY: "Word geometry was invalid.",
    NativeReasonCode.TEXT_OUTSIDE_PAGE_BOUNDS: "Text geometry fell outside page bounds.",
    NativeReasonCode.ZERO_AREA_TEXT_GEOMETRY: "Text geometry had zero area.",
    NativeReasonCode.EXCESSIVE_DUPLICATE_CHARACTERS: (
        "Excessive duplicate characters were detected."
    ),
    NativeReasonCode.EXCESSIVE_NEAR_OVERPRINT_DUPLICATES: (
        "The PDF contains overlapping native text layers that could not be "
        "trusted. Visual processing is required."
    ),
    NativeReasonCode.HIGH_SYMBOL_ONLY_WORD_RATIO: "Too many symbol-only words were present.",
    NativeReasonCode.HIGH_SINGLE_CHARACTER_WORD_RATIO: (
        "Too many single-character words were present."
    ),
    NativeReasonCode.IMPROBABLE_TOKEN_STRUCTURE: "Token structure was improbable.",
    NativeReasonCode.UNSTABLE_EXTRACTION_ORDER: "Extraction order was unstable.",
    NativeReasonCode.IMAGE_DOMINANT_PAGE: (
        "The page is image-dominant and requires visual processing."
    ),
    NativeReasonCode.CANONICAL_IMAGE_SOURCE: (
        "This page originates from an image and requires visual processing."
    ),
    NativeReasonCode.NATIVE_TRUST_SCORE_BELOW_THRESHOLD: (
        "The native trust score was below the acceptance threshold."
    ),
    NativeReasonCode.VISUAL_AGREEMENT_NOT_EVALUATED_PHASE_3: (
        "Visual agreement with the rendered page is not evaluated in Phase 3."
    ),
    NativeReasonCode.DOCUMENT_VISUAL_AUTHORITY_ESCALATION: (
        "The document was escalated to visual authority."
    ),
    NativeReasonCode.NATIVE_TEXT_REJECTED: "The native text layer was rejected.",
    NativeReasonCode.NATIVE_TEXT_NOT_VISUALLY_PRESENT: (
        "Accepted native text was not visually present on the rendered page."
    ),
    NativeReasonCode.NATIVE_TEXT_VISIBILITY_UNCERTAIN: (
        "Native text visibility could not be confirmed on the rendered page."
    ),
    NativeReasonCode.NATIVE_TEXT_VISUALLY_SUPPORTED: (
        "Accepted native text is supported by the rendered page."
    ),
    NativeReasonCode.OCR_NO_TEXT_DETECTED: "No printed text was detected.",
    NativeReasonCode.OCR_LOW_CONFIDENCE: "Printed OCR confidence was low for this page.",
    NativeReasonCode.VISUAL_PAGE_RESOURCE_LIMIT: (
        "The page exceeded visual rendering resource limits."
    ),
    NativeReasonCode.ISOLATED_PRIVATE_USE_GLYPH: ("An isolated private-use glyph was quarantined."),
    NativeReasonCode.UNSUPPORTED_CHECKBOX_GLYPH: (
        "An unsupported checkbox or form-mark glyph was quarantined."
    ),
    NativeReasonCode.SYMBOL_FONT_MAPPING_MISSING: (
        "A symbol-font glyph could not be mapped and was quarantined."
    ),
    NativeReasonCode.WIDESPREAD_UNICODE_CORRUPTION: (
        "This page required full visual OCR because the PDF text encoding was widely corrupt."
    ),
    NativeReasonCode.REPLACEMENT_CHARACTER_CORRUPTION: (
        "This page required full visual OCR because replacement-character "
        "corruption was widespread."
    ),
    NativeReasonCode.ISOLATED_GLYPHS_QUARANTINED: (
        "Some unsupported symbols were excluded pending visual verification."
    ),
    NativeReasonCode.MATERIAL_GLYPH_CORRUPTION: (
        "Corrupt glyphs affected material tokens and require visual verification."
    ),
}


def reason_message(code: str) -> str:
    """Return a safe generic message for a reason code."""

    try:
        return REASON_MESSAGES[NativeReasonCode(code)]
    except ValueError:
        return "A native trust warning was recorded."

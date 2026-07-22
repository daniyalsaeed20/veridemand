"""Helpers for recoverable page-level native extraction failures."""

from __future__ import annotations

from backend.app.contracts.native import (
    NativePageDecision,
    NativePageMetrics,
    NativePageResult,
    NativePageTrustResult,
    NativeWarning,
    ProvisionalOrderStatus,
    SourceMode,
    VisualAgreementStatus,
)
from backend.app.contracts.warnings import NativeReasonCode, reason_message


def empty_page_metrics(*, page_dimension_match: bool = True) -> NativePageMetrics:
    return NativePageMetrics(
        raw_character_count=0,
        deduplicated_character_count=0,
        word_count=0,
        character_count=0,
        duplicate_character_ratio=0.0,
        strict_duplicate_ratio=0.0,
        near_overprint_duplicate_ratio=0.0,
        duplicate_layer_count=1,
        dominant_duplicate_offset_x=0.0,
        dominant_duplicate_offset_y=0.0,
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
        alphanumeric_word_ratio=0.0,
        very_long_token_ratio=0.0,
        repeated_token_ratio=0.0,
        whitespace_ratio=0.0,
        font_count=0,
        missing_font_ratio=0.0,
        upright_character_ratio=0.0,
        extraction_order_backtrack_ratio=0.0,
        characters_per_page_area=0.0,
        words_per_page_area=0.0,
        image_count=0,
        largest_image_area_ratio=0.0,
        total_clipped_image_area_ratio=0.0,
        page_dimension_match=page_dimension_match,
        components=None,
    )


def build_recoverable_page_error(
    *,
    page_number: int,
    reason_codes: list[str] | None = None,
    trust_policy_version: str = "phase3-v1",
    page_dimension_match: bool = True,
) -> NativePageResult:
    """Text-free page result for recoverable content/parser failures."""

    codes = list(reason_codes or [NativeReasonCode.NATIVE_EXTRACTION_ERROR.value])
    if NativeReasonCode.NATIVE_EXTRACTION_ERROR.value not in codes:
        codes.insert(0, NativeReasonCode.NATIVE_EXTRACTION_ERROR.value)
    warnings = [
        NativeWarning(
            code=NativeReasonCode.VISUAL_AGREEMENT_NOT_EVALUATED_PHASE_3.value,
            message=reason_message(NativeReasonCode.VISUAL_AGREEMENT_NOT_EVALUATED_PHASE_3.value),
            page_number=page_number,
        )
    ]
    for code in codes:
        warnings.append(
            NativeWarning(code=code, message=reason_message(code), page_number=page_number)
        )
    trust = NativePageTrustResult(
        page_number=page_number,
        decision=NativePageDecision.ERROR,
        source_mode=SourceMode.VISUAL_AUTHORITY,
        native_text_present=False,
        native_trust_score=None,
        trust_policy_version=trust_policy_version,
        hard_rejection=True,
        reason_codes=codes,
        warning_codes=[NativeReasonCode.VISUAL_AGREEMENT_NOT_EVALUATED_PHASE_3.value],
        metrics=empty_page_metrics(page_dimension_match=page_dimension_match),
        visual_agreement_status=VisualAgreementStatus.NOT_EVALUATED_PHASE_3,
        visual_agreement_score=None,
        native_result_available=False,
        visual_processing_required=True,
    )
    return NativePageResult(
        page_number=page_number,
        decision=NativePageDecision.ERROR,
        source_mode=SourceMode.VISUAL_AUTHORITY,
        trust=trust,
        provisional_order_status=ProvisionalOrderStatus.UNVERIFIED,
        words=[],
        characters=[],
        provisional_native_text=None,
        warnings=warnings,
    )


# Exception types treated as recoverable content/parser failures (not infra).
RECOVERABLE_EXCEPTION_TYPES: tuple[type[BaseException], ...] = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ArithmeticError,
    UnicodeError,
    OSError,  # pdfminer I/O on a page stream — recoverable as page error when mid-page
)

try:
    from pdfminer.pdfparser import PDFSyntaxError as _PDFSyntaxError

    RECOVERABLE_EXCEPTION_TYPES = (*RECOVERABLE_EXCEPTION_TYPES, _PDFSyntaxError)
except Exception:  # pragma: no cover - optional import shape
    pass

try:
    from pdfminer.psparser import PSException as _PSException

    RECOVERABLE_EXCEPTION_TYPES = (*RECOVERABLE_EXCEPTION_TYPES, _PSException)
except Exception:  # pragma: no cover
    pass


def is_recoverable_content_exception(exc: BaseException) -> bool:
    """Return True when the failure should become a page-level visual_authority error."""

    if isinstance(exc, MemoryError):
        return False
    if isinstance(exc, KeyboardInterrupt):
        return False
    name = type(exc).__name__
    module = type(exc).__module__ or ""
    if "pdfminer" in module or "pdfplumber" in module:
        return True
    if name in {"PDFSyntaxError", "PDFPasswordIncorrect", "PSEOF", "PSSyntaxError"}:
        return True
    return isinstance(exc, RECOVERABLE_EXCEPTION_TYPES)

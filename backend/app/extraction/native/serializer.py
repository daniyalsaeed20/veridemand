"""Serialise native pages; retain verification boxes for non-accepted pages."""

from __future__ import annotations

from backend.app.contracts.canonical import CanonicalisationMethod
from backend.app.contracts.native import (
    NativeCharacter,
    NativePageDecision,
    NativePageResult,
    NativeWarning,
    NativeWord,
    ProvisionalOrderStatus,
    RecognitionMethod,
    RecognitionStatus,
    SourceMode,
)
from backend.app.contracts.warnings import reason_message
from backend.app.extraction.native.trust_policy import PageTrustDecisionBundle
from backend.app.extraction.native.unicode_quality import nfc, unicode_category_for


def _recognition_method(method: str) -> RecognitionMethod:
    if method == CanonicalisationMethod.ORIGINAL_PDF.value:
        return RecognitionMethod.NATIVE_PDF
    return RecognitionMethod.CANONICAL_PDF_NATIVE


def as_verification_words(words: list[NativeWord]) -> list[NativeWord]:
    """Copy words with recognition_status=rejected for diagnostic retention."""

    return [w.model_copy(update={"recognition_status": RecognitionStatus.REJECTED}) for w in words]


def _build_words_and_characters(
    bundle: PageTrustDecisionBundle,
    *,
    canonicalisation_method: str,
    recognition_status: RecognitionStatus,
) -> tuple[list[NativeWord], list[NativeCharacter]]:
    page_no = bundle.trust.page_number
    characters: list[NativeCharacter] = []
    for geom_result in bundle.geometry.char_results:
        if geom_result.mapped.invalid or geom_result.mapped.out_of_bounds:
            continue
        cand = geom_result.candidate
        seq = cand.sequence_index
        char_id = f"char_p{page_no:04d}_{seq + 1:06d}"
        text = cand.text
        characters.append(
            NativeCharacter(
                id=char_id,
                page_number=page_no,
                sequence_index=seq,
                text=text,
                normalised_text=nfc(text),
                font_name=cand.fontname,
                font_size=cand.size,
                upright=cand.upright,
                rotation_degrees=cand.rotation_degrees,
                geometry=geom_result.mapped.geometry,
                pdf_point_bbox=geom_result.mapped.pdf_point_bbox,
                unicode_category=unicode_category_for(text),
                is_whitespace=text.isspace(),
            )
        )

    published_set = {c.id for c in characters}
    index_to_id: dict[int, str] = {}
    for i, geom_result in enumerate(bundle.geometry.char_results):
        cand = geom_result.candidate
        char_id = f"char_p{page_no:04d}_{cand.sequence_index + 1:06d}"
        if char_id in published_set:
            index_to_id[i] = char_id

    method = _recognition_method(canonicalisation_method)
    words: list[NativeWord] = []
    for word_result in bundle.geometry.word_results:
        if word_result.mapped.invalid or not word_result.contains_chars:
            continue
        word = word_result.candidate
        linked_ids = [index_to_id[i] for i in word.char_indices if i in index_to_id]
        word_id = f"word_p{page_no:04d}_{word.sequence_index + 1:06d}"
        words.append(
            NativeWord(
                id=word_id,
                page_number=page_no,
                sequence_index=word.sequence_index,
                text=word.text,
                normalised_text=nfc(word.text),
                character_ids=linked_ids,
                geometry=word_result.mapped.geometry,
                pdf_point_bbox=word_result.mapped.pdf_point_bbox,
                font_names=word.fontnames,
                font_sizes=word.sizes,
                upright=word.upright,
                recognition_method=method,
                source_mode=SourceMode.NATIVE_AUTHORITY,
                recognition_status=recognition_status,
            )
        )
    return words, characters


def build_page_result(
    bundle: PageTrustDecisionBundle,
    *,
    canonicalisation_method: str,
) -> NativePageResult:
    trust = bundle.trust
    warnings = [
        NativeWarning(code=code, message=reason_message(code), page_number=trust.page_number)
        for code in [*trust.reason_codes, *trust.warning_codes]
    ]

    if not bundle.accept_text:
        verification_words, _chars = _build_words_and_characters(
            bundle,
            canonicalisation_method=canonicalisation_method,
            recognition_status=RecognitionStatus.REJECTED,
        )
        return NativePageResult(
            page_number=trust.page_number,
            decision=trust.decision,
            source_mode=trust.source_mode,
            trust=trust,
            provisional_order_status=ProvisionalOrderStatus.UNVERIFIED,
            words=[],
            characters=[],
            provisional_native_text=None,
            verification_words=verification_words,
            warnings=warnings,
        )

    words, characters = _build_words_and_characters(
        bundle,
        canonicalisation_method=canonicalisation_method,
        recognition_status=RecognitionStatus.ACCEPTED,
    )
    provisional = " ".join(w.text for w in words) if words else None
    return NativePageResult(
        page_number=trust.page_number,
        decision=NativePageDecision.ACCEPTED,
        source_mode=SourceMode.NATIVE_AUTHORITY,
        trust=trust,
        provisional_order_status=ProvisionalOrderStatus.UNVERIFIED,
        words=words,
        characters=characters,
        provisional_native_text=provisional,
        verification_words=[],
        warnings=warnings,
    )


def page_result_for_storage(
    page: NativePageResult, *, include_characters: bool
) -> dict[str, object]:
    """Dump a page result; optionally omit characters for the default API.

    Non-accepted pages keep ``verification_words`` for Phase 4.5; accepted
    fields (``words`` / ``characters`` / ``provisional_native_text``) stay empty.
    """

    data = page.model_dump(mode="json")
    if not include_characters:
        data["characters"] = []
    if page.decision is not NativePageDecision.ACCEPTED:
        data["words"] = []
        data["characters"] = []
        data["provisional_native_text"] = None
        # Retain verification_words (diagnostic / Phase 4.5).
    return data


def page_result_for_public_api(
    page: NativePageResult,
    *,
    include_characters: bool = False,
    include_verification_candidates: bool = False,
) -> NativePageResult:
    """Public API view: never expose verification candidates unless explicitly requested."""

    updates: dict[str, object] = {}
    if not include_characters:
        updates["characters"] = []
    if page.decision is not NativePageDecision.ACCEPTED:
        updates["words"] = []
        updates["characters"] = []
        updates["provisional_native_text"] = None
    if not include_verification_candidates:
        updates["verification_words"] = []
    if not updates:
        return page
    return page.model_copy(update=updates)

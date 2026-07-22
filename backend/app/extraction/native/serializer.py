"""Serialise accepted native pages; strip text from rejected pages."""

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
        return NativePageResult(
            page_number=trust.page_number,
            decision=trust.decision,
            source_mode=trust.source_mode,
            trust=trust,
            provisional_order_status=ProvisionalOrderStatus.UNVERIFIED,
            words=[],
            characters=[],
            provisional_native_text=None,
            warnings=warnings,
        )

    page_no = trust.page_number
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

    # Map original candidate index → published character id.
    published_by_index: dict[int, str] = {}
    published_set = {c.id for c in characters}
    for geom_result in bundle.geometry.char_results:
        cand = geom_result.candidate
        char_id = f"char_p{page_no:04d}_{cand.sequence_index + 1:06d}"
        if char_id in published_set:
            published_by_index[cand.sequence_index] = char_id

    # Rebuild index map from char_indices (which point into page.characters list).
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
                recognition_status=RecognitionStatus.ACCEPTED,
            )
        )

    provisional = " ".join(w.text for w in words) if words else None
    return NativePageResult(
        page_number=page_no,
        decision=NativePageDecision.ACCEPTED,
        source_mode=SourceMode.NATIVE_AUTHORITY,
        trust=trust,
        provisional_order_status=ProvisionalOrderStatus.UNVERIFIED,
        words=words,
        characters=characters,
        provisional_native_text=provisional,
        warnings=warnings,
    )


def page_result_for_storage(
    page: NativePageResult, *, include_characters: bool
) -> dict[str, object]:
    """Dump a page result; optionally omit characters for the default API."""

    data = page.model_dump(mode="json")
    if not include_characters:
        data["characters"] = []
    # Rejected/suppressed pages must never carry text fields.
    if page.decision is not NativePageDecision.ACCEPTED:
        data["words"] = []
        data["characters"] = []
        data["provisional_native_text"] = None
    return data

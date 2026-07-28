"""Page-local glyph quarantine and materiality (Correction 3).

Isolated unsupported glyphs (private-use checkboxes, symbol-font stand-ins) are
quarantined without rejecting an otherwise coherent page. Widespread Unicode
corruption and material identifier corruption remain hard-rejected.

Never logs or returns quarantined strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from backend.app.contracts.warnings import NativeReasonCode
from backend.app.extraction.native.models import (
    NativeTrustPolicyConfig,
    PageExtractionCandidate,
    RawCharCandidate,
    RawWordCandidate,
)
from backend.app.extraction.native.unicode_quality import (
    _CHECKBOX_LIKE,
    char_is_invalid_for_quarantine,
)

GLYPH_QUARANTINE_POLICY_VERSION = "phase4-c3-v1"

_NUMERIC_OR_DATE_RE = re.compile(
    r"""
    (?:
        \d{1,4}[-/\.]\d{1,2}[-/\.]\d{1,4}   # date-like
        | \d+[.,]\d+                         # decimal
        | \$\s*\d                            # currency
        | \d{3,}                             # multi-digit identifier
    )
    """,
    re.VERBOSE,
)


class GlyphMateriality(StrEnum):
    NONE = "none"
    NON_MATERIAL = "non_material"
    MATERIAL = "material"
    WIDESPREAD = "widespread"


class GlyphCorruptionClass(StrEnum):
    """Disjoint corruption diagnostics (A-D)."""

    WIDESPREAD_ORDINARY = "A_widespread_ordinary_corruption"
    ISOLATED_SYMBOLIC = "B_isolated_symbolic_glyphs"
    MISSING_TOUNICODE = "C_missing_tounicode"
    CHECKBOX_ICON = "D_checkbox_icon_glyphs"


@dataclass(frozen=True, slots=True)
class GlyphMaterialityPolicy:
    """Structural materiality knobs — no semantic fact extraction."""

    policy_version: str = GLYPH_QUARANTINE_POLICY_VERSION
    max_non_material_invalid_char_ratio: float = 0.08
    max_non_material_invalid_token_ratio: float = 0.18
    max_non_material_affected_words: int = 48
    max_non_material_affected_lines: int = 24
    max_non_material_spatial_coverage: float = 0.10
    min_ordinary_char_count_for_salvage: int = 40
    widespread_invalid_char_ratio: float = 0.15
    widespread_replacement_ratio: float = 0.05
    material_numeric_invalid_is_material: bool = True


@dataclass(frozen=True, slots=True)
class QuarantinedGlyphRegion:
    """Internal quarantine record — never exposes glyph strings."""

    page_number: int
    source_word_id: int | None
    x0: float
    x1: float
    top: float
    bottom: float
    unicode_category: str
    safe_reason_code: str
    repair_eligible: bool
    materiality: GlyphMateriality
    policy_version: str
    char_sequence_index: int | None = None


@dataclass(slots=True)
class GlyphQuarantineResult:
    page: PageExtractionCandidate
    regions: list[QuarantinedGlyphRegion] = field(default_factory=list)
    warning_codes: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    materiality: GlyphMateriality = GlyphMateriality.NONE
    corruption_class: GlyphCorruptionClass | None = None
    salvage_applied: bool = False
    quarantined_glyph_count: int = 0
    quarantined_region_count: int = 0
    repair_eligible: bool = False
    policy_version: str = GLYPH_QUARANTINE_POLICY_VERSION


def _safe_reason_for_char(ch: str, cat: str) -> str:
    cp = ord(ch) if ch else 0
    if ch == "\ufffd":
        return NativeReasonCode.REPLACEMENT_CHARACTER_CORRUPTION.value
    if cp in _CHECKBOX_LIKE or cat == "Co":
        return NativeReasonCode.UNSUPPORTED_CHECKBOX_GLYPH.value
    if cat.startswith("S"):
        return NativeReasonCode.SYMBOL_FONT_MAPPING_MISSING.value
    if cat in {"Cc", "Cs", "Cn"}:
        return NativeReasonCode.ISOLATED_PRIVATE_USE_GLYPH.value
    return NativeReasonCode.ISOLATED_PRIVATE_USE_GLYPH.value


def _word_is_numeric_or_date(text: str) -> bool:
    if _NUMERIC_OR_DATE_RE.search(text or ""):
        return True
    cleaned = "".join(ch for ch in (text or "") if not char_is_invalid_for_quarantine(ch)[0])
    return bool(_NUMERIC_OR_DATE_RE.search(cleaned))


def _line_key(word: RawWordCandidate) -> int:
    # Bucket by top coordinate for approximate line count.
    return round(word.top / 4.0)


def _spatial_coverage(
    regions: list[QuarantinedGlyphRegion], page: PageExtractionCandidate
) -> float:
    if not regions:
        return 0.0
    area = 0.0
    page_area = max(page.page_width * page.page_height, 1.0)
    for r in regions:
        area += max(r.x1 - r.x0, 0.0) * max(r.bottom - r.top, 0.0)
    return min(area / page_area, 1.0)


def evaluate_glyph_materiality(
    *,
    page: PageExtractionCandidate,
    invalid_char_indices: set[int],
    regions: list[QuarantinedGlyphRegion],
    replacement_ratio: float,
    private_use_ratio: float,
    checkbox_like_ratio: float,
    policy: GlyphMaterialityPolicy,
) -> tuple[GlyphMateriality, GlyphCorruptionClass, bool]:
    """Return (materiality, corruption_class, salvage_allowed)."""

    non_ws = [c for c in page.characters if not c.text.isspace()]
    total = max(len(non_ws), 1)
    invalid_count = len(invalid_char_indices)
    invalid_char_ratio = invalid_count / total

    if replacement_ratio >= policy.widespread_replacement_ratio:
        return (
            GlyphMateriality.WIDESPREAD,
            GlyphCorruptionClass.MISSING_TOUNICODE,
            False,
        )
    if invalid_char_ratio >= policy.widespread_invalid_char_ratio:
        return (
            GlyphMateriality.WIDESPREAD,
            GlyphCorruptionClass.WIDESPREAD_ORDINARY,
            False,
        )

    affected_words = 0
    mixed_invalid_words = 0
    material_numeric = False
    symbol_only_invalid_words = 0
    for word in page.words:
        idxs = [i for i in word.char_indices if i in invalid_char_indices]
        has_embedded_invalid = any(char_is_invalid_for_quarantine(ch)[0] for ch in word.text)
        if not idxs and not has_embedded_invalid:
            continue
        affected_words += 1
        if policy.material_numeric_invalid_is_material and _word_is_numeric_or_date(word.text):
            material_numeric = True
        if idxs:
            remaining = "".join(
                page.characters[i].text
                for i in word.char_indices
                if i not in invalid_char_indices and i < len(page.characters)
            )
            if not remaining.strip():
                symbol_only_invalid_words += 1
            else:
                mixed_invalid_words += 1
        elif all(char_is_invalid_for_quarantine(ch)[0] or ch.isspace() for ch in word.text):
            symbol_only_invalid_words += 1
        else:
            mixed_invalid_words += 1

    # Token-ratio pressure counts mixed corruption only; pure checkbox tokens are capped
    # absolutely via max_non_material_affected_words.
    invalid_token_ratio = mixed_invalid_words / max(len(page.words), 1)
    line_ids = {
        _line_key(w)
        for w in page.words
        if any(i in invalid_char_indices for i in w.char_indices)
        or any(char_is_invalid_for_quarantine(ch)[0] for ch in w.text)
    }
    spatial = _spatial_coverage(regions, page)
    ordinary_chars = total - invalid_count

    mostly_checkbox = (
        checkbox_like_ratio >= private_use_ratio * 0.8
        and private_use_ratio > 0
        and symbol_only_invalid_words >= max(1, int(affected_words * 0.5))
    )

    if material_numeric:
        return (
            GlyphMateriality.MATERIAL,
            GlyphCorruptionClass.WIDESPREAD_ORDINARY
            if invalid_char_ratio > 0.05
            else GlyphCorruptionClass.ISOLATED_SYMBOLIC,
            False,
        )

    non_material = (
        invalid_char_ratio <= policy.max_non_material_invalid_char_ratio
        and invalid_token_ratio <= policy.max_non_material_invalid_token_ratio
        and affected_words <= policy.max_non_material_affected_words
        and len(line_ids) <= policy.max_non_material_affected_lines
        and spatial <= policy.max_non_material_spatial_coverage
        and ordinary_chars >= policy.min_ordinary_char_count_for_salvage
    )
    if non_material:
        corruption = (
            GlyphCorruptionClass.CHECKBOX_ICON
            if mostly_checkbox
            else GlyphCorruptionClass.ISOLATED_SYMBOLIC
        )
        return GlyphMateriality.NON_MATERIAL, corruption, True

    # Checkbox-dominated pages with coherent ordinary text: salvage when mixed
    # corruption is absent and absolute checkbox count stays within the word cap.
    if (
        mostly_checkbox
        and mixed_invalid_words == 0
        and not material_numeric
        and ordinary_chars >= policy.min_ordinary_char_count_for_salvage
        and affected_words <= policy.max_non_material_affected_words
        and invalid_char_ratio <= policy.max_non_material_invalid_char_ratio
    ):
        return GlyphMateriality.NON_MATERIAL, GlyphCorruptionClass.CHECKBOX_ICON, True

    return (
        GlyphMateriality.MATERIAL,
        GlyphCorruptionClass.ISOLATED_SYMBOLIC,
        False,
    )


def _rebuild_page_without_invalid(
    page: PageExtractionCandidate,
    invalid_char_indices: set[int],
) -> PageExtractionCandidate:
    """Drop invalid characters and rebuild words without exposing corrupt text."""

    new_chars: list[RawCharCandidate] = []
    old_to_new: dict[int, int] = {}
    for idx, ch in enumerate(page.characters):
        if idx in invalid_char_indices:
            continue
        old_to_new[idx] = len(new_chars)
        new_chars.append(
            RawCharCandidate(
                text=ch.text,
                fontname=ch.fontname,
                size=ch.size,
                upright=ch.upright,
                rotation_degrees=ch.rotation_degrees,
                x0=ch.x0,
                x1=ch.x1,
                top=ch.top,
                bottom=ch.bottom,
                sequence_index=len(new_chars),
                tagged=ch.tagged,
            )
        )

    new_words: list[RawWordCandidate] = []
    for word in page.words:
        kept_indices = [old_to_new[i] for i in word.char_indices if i in old_to_new]
        if not kept_indices:
            # Entire word was invalid glyphs — drop from public candidates.
            continue
        text = "".join(new_chars[i].text for i in kept_indices)
        if not text.strip():
            continue
        # If residual invalid slipped into text without indices, strip structurally.
        cleaned = "".join(ch for ch in text if not char_is_invalid_for_quarantine(ch)[0])
        if not cleaned.strip():
            continue
        xs = [new_chars[i].x0 for i in kept_indices] + [new_chars[i].x1 for i in kept_indices]
        ys_top = [new_chars[i].top for i in kept_indices]
        ys_bot = [new_chars[i].bottom for i in kept_indices]
        new_words.append(
            RawWordCandidate(
                text=cleaned if cleaned != text else text,
                x0=min(xs),
                x1=max(xs),
                top=min(ys_top),
                bottom=max(ys_bot),
                sequence_index=len(new_words),
                char_indices=kept_indices,
                fontnames=list(word.fontnames),
                sizes=list(word.sizes),
                upright=word.upright,
            )
        )

    return PageExtractionCandidate(
        page_number=page.page_number,
        page_width=page.page_width,
        page_height=page.page_height,
        page_bbox_x0=page.page_bbox_x0,
        page_bbox_top=page.page_bbox_top,
        raw_character_count=len(new_chars),
        characters=new_chars,
        words=new_words,
        images=list(page.images),
        page_dimension_match=page.page_dimension_match,
        extraction_error=page.extraction_error,
        strict_duplicate_ratio=page.strict_duplicate_ratio,
        near_overprint_duplicate_ratio=page.near_overprint_duplicate_ratio,
        duplicate_layer_count=page.duplicate_layer_count,
        dominant_duplicate_offset_x=page.dominant_duplicate_offset_x,
        dominant_duplicate_offset_y=page.dominant_duplicate_offset_y,
        duplicate_layer_coverage_ratio=page.duplicate_layer_coverage_ratio,
        matched_near_duplicate_count=page.matched_near_duplicate_count,
        dominant_offset_support_ratio=page.dominant_offset_support_ratio,
        matched_word_span=page.matched_word_span,
        matched_line_span=page.matched_line_span,
        top_offset_cluster_support_ratio=page.top_offset_cluster_support_ratio,
        top_k_offset_cluster_support_ratio=page.top_k_offset_cluster_support_ratio,
        offset_cluster_count=page.offset_cluster_count,
        duplicate_line_count=page.duplicate_line_count,
        duplicate_region_count=page.duplicate_region_count,
        page_vertical_span_ratio=page.page_vertical_span_ratio,
        page_horizontal_span_ratio=page.page_horizontal_span_ratio,
        hard_rule_path=page.hard_rule_path,
        hard_rule_explanation=page.hard_rule_explanation,
        duplicate_layer_evidence=page.duplicate_layer_evidence,
        near_overprint_composite_evidence=page.near_overprint_composite_evidence,
        near_overprint_cleaned=page.near_overprint_cleaned,
        near_overprint_ambiguous=page.near_overprint_ambiguous,
    )


def apply_glyph_quarantine(
    page: PageExtractionCandidate,
    trust_policy: NativeTrustPolicyConfig,
    *,
    materiality_policy: GlyphMaterialityPolicy | None = None,
) -> GlyphQuarantineResult:
    """Quarantine isolated invalid glyphs when materiality allows salvage."""

    mat_policy = materiality_policy or GlyphMaterialityPolicy()
    if not page.characters:
        return GlyphQuarantineResult(page=page)

    invalid_indices: set[int] = set()
    regions: list[QuarantinedGlyphRegion] = []
    replacement = 0
    private_use = 0
    checkbox_like = 0
    non_ws_total = 0

    # Map char index → owning word id
    char_to_word: dict[int, int] = {}
    for wi, word in enumerate(page.words):
        for ci in word.char_indices:
            char_to_word[ci] = wi

    for idx, cand in enumerate(page.characters):
        ch = cand.text
        if ch.isspace():
            continue
        non_ws_total += 1
        invalid, cat = char_is_invalid_for_quarantine(ch)
        cp = ord(ch)
        if ch == "\ufffd":
            replacement += 1
        if cat == "Co":
            private_use += 1
        if cp in _CHECKBOX_LIKE or cat == "Co":
            checkbox_like += 1
        if not invalid:
            continue
        invalid_indices.add(idx)
        reason = _safe_reason_for_char(ch, cat)
        regions.append(
            QuarantinedGlyphRegion(
                page_number=page.page_number,
                source_word_id=char_to_word.get(idx),
                x0=cand.x0,
                x1=cand.x1,
                top=cand.top,
                bottom=cand.bottom,
                unicode_category=cat,
                safe_reason_code=reason,
                repair_eligible=True,
                materiality=GlyphMateriality.NON_MATERIAL,
                policy_version=mat_policy.policy_version,
                char_sequence_index=cand.sequence_index,
            )
        )

    if not invalid_indices:
        return GlyphQuarantineResult(page=page)

    total = max(non_ws_total, 1)
    replacement_ratio = replacement / total
    private_use_ratio = private_use / total
    checkbox_like_ratio = checkbox_like / total

    materiality, corruption, salvage_ok = evaluate_glyph_materiality(
        page=page,
        invalid_char_indices=invalid_indices,
        regions=regions,
        replacement_ratio=replacement_ratio,
        private_use_ratio=private_use_ratio,
        checkbox_like_ratio=checkbox_like_ratio,
        policy=mat_policy,
    )

    # Update region materiality flags.
    regions = [
        QuarantinedGlyphRegion(
            page_number=r.page_number,
            source_word_id=r.source_word_id,
            x0=r.x0,
            x1=r.x1,
            top=r.top,
            bottom=r.bottom,
            unicode_category=r.unicode_category,
            safe_reason_code=r.safe_reason_code,
            repair_eligible=materiality is GlyphMateriality.MATERIAL,
            materiality=materiality,
            policy_version=r.policy_version,
            char_sequence_index=r.char_sequence_index,
        )
        for r in regions
    ]

    if materiality is GlyphMateriality.WIDESPREAD:
        reason = (
            NativeReasonCode.REPLACEMENT_CHARACTER_CORRUPTION.value
            if corruption is GlyphCorruptionClass.MISSING_TOUNICODE
            else NativeReasonCode.WIDESPREAD_UNICODE_CORRUPTION.value
        )
        return GlyphQuarantineResult(
            page=page,
            regions=regions,
            reason_codes=[reason],
            materiality=materiality,
            corruption_class=corruption,
            salvage_applied=False,
            quarantined_glyph_count=len(invalid_indices),
            quarantined_region_count=len(regions),
            repair_eligible=False,
            policy_version=mat_policy.policy_version,
        )

    if materiality is GlyphMateriality.MATERIAL or not salvage_ok:
        return GlyphQuarantineResult(
            page=page,
            regions=regions,
            reason_codes=[NativeReasonCode.MATERIAL_GLYPH_CORRUPTION.value],
            materiality=materiality,
            corruption_class=corruption,
            salvage_applied=False,
            quarantined_glyph_count=len(invalid_indices),
            quarantined_region_count=len(regions),
            repair_eligible=True,
            policy_version=mat_policy.policy_version,
        )

    salvaged = _rebuild_page_without_invalid(page, invalid_indices)
    warnings = [
        NativeReasonCode.ISOLATED_GLYPHS_QUARANTINED.value,
    ]
    if corruption is GlyphCorruptionClass.CHECKBOX_ICON:
        warnings.append(NativeReasonCode.UNSUPPORTED_CHECKBOX_GLYPH.value)
    elif any(
        r.safe_reason_code == NativeReasonCode.ISOLATED_PRIVATE_USE_GLYPH.value for r in regions
    ):
        warnings.append(NativeReasonCode.ISOLATED_PRIVATE_USE_GLYPH.value)
    elif any(
        r.safe_reason_code == NativeReasonCode.SYMBOL_FONT_MAPPING_MISSING.value for r in regions
    ):
        warnings.append(NativeReasonCode.SYMBOL_FONT_MAPPING_MISSING.value)

    # Silence unused trust_policy for now (thresholds stay authoritative after rescore).
    _ = trust_policy

    return GlyphQuarantineResult(
        page=salvaged,
        regions=regions,
        warning_codes=warnings,
        materiality=materiality,
        corruption_class=corruption,
        salvage_applied=True,
        quarantined_glyph_count=len(invalid_indices),
        quarantined_region_count=len(regions),
        repair_eligible=False,
        policy_version=mat_policy.policy_version,
    )

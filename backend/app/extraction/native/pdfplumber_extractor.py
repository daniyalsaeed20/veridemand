"""Candidate native character/word extraction with pdfplumber."""

from __future__ import annotations

from pathlib import Path

import pdfplumber
from backend.app.extraction.native.models import (
    CanonicalPageRef,
    ImageGeom,
    NativeTrustPolicyConfig,
    PageExtractionCandidate,
    RawCharCandidate,
    RawWordCandidate,
)
from backend.app.extraction.native.near_overprint import analyse_and_clean_near_overprint


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _char_tagged(ch: dict[str, object]) -> bool | None:
    """Best-effort tagged-object hint from pdfplumber/pdfminer char dicts."""

    if "tag" in ch and ch["tag"] is not None:
        return True
    if ch.get("mcid") is not None:
        return True
    if ch.get("tagged") is True:
        return True
    if ch.get("tagged") is False:
        return False
    return None


def extract_page_candidates(
    pdf_path: Path,
    pages: list[CanonicalPageRef],
    policy: NativeTrustPolicyConfig,
) -> list[PageExtractionCandidate]:
    """Extract candidate characters and words for each canonical page."""

    results: list[PageExtractionCandidate] = []
    try:
        pdf_cm = pdfplumber.open(str(pdf_path), unicode_norm="NFC", strict_metadata=False)
    except Exception:
        # Document-level open failure: caller may contain as all-page errors.
        raise
    with pdf_cm as pdf:
        if len(pdf.pages) != len(pages):
            for meta in pages:
                results.append(
                    PageExtractionCandidate(
                        page_number=meta.page_number,
                        page_width=meta.width_points,
                        page_height=meta.height_points,
                        page_bbox_x0=0.0,
                        page_bbox_top=0.0,
                        raw_character_count=0,
                        characters=[],
                        words=[],
                        images=[],
                        page_dimension_match=False,
                        extraction_error="page_count_mismatch",
                    )
                )
            return results

        for meta, page in zip(pages, pdf.pages, strict=True):
            try:
                results.append(_extract_one_page(meta, page, policy))
            except Exception:
                results.append(
                    PageExtractionCandidate(
                        page_number=meta.page_number,
                        page_width=meta.width_points,
                        page_height=meta.height_points,
                        page_bbox_x0=0.0,
                        page_bbox_top=0.0,
                        raw_character_count=0,
                        characters=[],
                        words=[],
                        images=[],
                        page_dimension_match=False,
                        extraction_error="page_extraction_failed",
                    )
                )
            finally:
                # Release per-page caches when available.
                flush = getattr(page, "flush_cache", None)
                if callable(flush):
                    flush()
                close = getattr(page, "close", None)
                if callable(close):
                    close()
    return results


def _extract_one_page(
    meta: CanonicalPageRef,
    page: pdfplumber.page.Page,
    policy: NativeTrustPolicyConfig,
) -> PageExtractionCandidate:
    page_width = float(page.width)
    page_height = float(page.height)
    bbox = page.bbox  # (x0, top, x1, bottom) in pdfplumber top-origin space
    page_bbox_x0 = float(bbox[0])
    page_bbox_top = float(bbox[1])

    dim_tol = policy.canonical_page_dimension_tolerance_points
    page_dimension_match = (
        abs(page_width - meta.width_points) <= dim_tol
        and abs(page_height - meta.height_points) <= dim_tol
    )

    raw_chars = list(page.chars or [])
    raw_character_count = len(raw_chars)

    deduped = page.dedupe_chars(
        tolerance=policy.native_dedupe_tolerance_points,
        extra_attrs=("fontname", "size"),
    )
    deduped_chars = list(deduped.chars or [])

    characters: list[RawCharCandidate] = []
    for index, ch in enumerate(deduped_chars):
        text = str(ch.get("text") or "")
        if text == "":
            continue
        characters.append(
            RawCharCandidate(
                text=text,
                fontname=str(ch["fontname"]) if ch.get("fontname") is not None else None,
                size=max(_safe_float(ch.get("size"), 0.0), 0.0),
                upright=bool(ch.get("upright", True)),
                rotation_degrees=_char_rotation(ch),
                x0=_safe_float(ch.get("x0")),
                x1=_safe_float(ch.get("x1")),
                top=_safe_float(ch.get("top")),
                bottom=_safe_float(ch.get("bottom")),
                sequence_index=index,
                tagged=_char_tagged(ch),
            )
        )

    strict_duplicate_ratio = (raw_character_count - len(characters)) / max(raw_character_count, 1)

    word_dicts = deduped.extract_words(
        x_tolerance=3,
        y_tolerance=3,
        keep_blank_chars=False,
        use_text_flow=False,
        line_dir="ttb",
        char_dir="ltr",
        line_dir_rotated="ttb",
        char_dir_rotated="ltr",
        split_at_punctuation=False,
        expand_ligatures=True,
        return_chars=True,
    )

    words: list[RawWordCandidate] = []
    for index, wd in enumerate(word_dicts or []):
        text = str(wd.get("text") or "").strip()
        if not text:
            continue
        linked = wd.get("chars") or []
        char_indices: list[int] = []
        fontnames: list[str] = []
        sizes: list[float] = []
        upright = True
        for linked_ch in linked:
            # Match by geometry against deduped character list.
            lx0 = _safe_float(linked_ch.get("x0"))
            ltop = _safe_float(linked_ch.get("top"))
            ltext = str(linked_ch.get("text") or "")
            for ci, cand in enumerate(characters):
                if (
                    cand.text == ltext
                    and abs(cand.x0 - lx0) < 0.01
                    and abs(cand.top - ltop) < 0.01
                    and ci not in char_indices
                ):
                    char_indices.append(ci)
                    if cand.fontname:
                        fontnames.append(cand.fontname)
                    sizes.append(cand.size)
                    upright = upright and cand.upright
                    break
        words.append(
            RawWordCandidate(
                text=text,
                x0=_safe_float(wd.get("x0")),
                x1=_safe_float(wd.get("x1")),
                top=_safe_float(wd.get("top")),
                bottom=_safe_float(wd.get("bottom")),
                sequence_index=index,
                char_indices=char_indices,
                fontnames=sorted(set(fontnames)),
                sizes=sorted(set(sizes)),
                upright=upright,
            )
        )

    overprint = analyse_and_clean_near_overprint(
        characters,
        strict_duplicate_ratio=strict_duplicate_ratio,
        words=words,
        max_near_overprint_ratio=policy.native_max_near_overprint_ratio,
        iou_threshold=policy.native_near_overprint_iou_threshold,
        centre_factor=policy.native_near_overprint_centre_factor,
        centre_cap=policy.native_near_overprint_centre_cap_points,
        size_similarity=policy.native_near_overprint_size_similarity,
    )
    characters = overprint.characters
    words = overprint.words
    near_overprint_ambiguous = overprint.selection == "ambiguous"

    images: list[ImageGeom] = []
    for img in page.images or []:
        images.append(
            ImageGeom(
                x0=_safe_float(img.get("x0")),
                x1=_safe_float(img.get("x1")),
                top=_safe_float(img.get("top")),
                bottom=_safe_float(img.get("bottom")),
            )
        )

    return PageExtractionCandidate(
        page_number=meta.page_number,
        page_width=page_width,
        page_height=page_height,
        page_bbox_x0=page_bbox_x0,
        page_bbox_top=page_bbox_top,
        raw_character_count=raw_character_count,
        characters=characters,
        words=words,
        images=images,
        page_dimension_match=page_dimension_match,
        strict_duplicate_ratio=overprint.metrics.strict_duplicate_ratio,
        near_overprint_duplicate_ratio=overprint.metrics.near_overprint_duplicate_ratio,
        duplicate_layer_count=overprint.metrics.duplicate_layer_count,
        dominant_duplicate_offset_x=overprint.metrics.dominant_duplicate_offset_x,
        dominant_duplicate_offset_y=overprint.metrics.dominant_duplicate_offset_y,
        near_overprint_ambiguous=near_overprint_ambiguous,
    )


def _char_rotation(ch: dict[str, object]) -> float:
    """Best-effort character rotation from pdfplumber attributes."""

    if "matrix" in ch and isinstance(ch["matrix"], (list, tuple)) and len(ch["matrix"]) >= 4:
        # Approximate rotation from transformation matrix a,b,c,d.
        import math

        a = _safe_float(ch["matrix"][0], 1.0)
        b = _safe_float(ch["matrix"][1], 0.0)
        return math.degrees(math.atan2(b, a))
    return 0.0

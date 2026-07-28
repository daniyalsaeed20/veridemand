"""Materialise verified embedded OCR candidates into public visual page results."""

from __future__ import annotations

import logging
import math
import unicodedata
from dataclasses import dataclass

from backend.app.contracts.geometry import (
    Geometry,
    NormalisedBoundingBox,
    NormalisedPoint,
    NormalisedPolygon,
)
from backend.app.contracts.native import NativeWord
from backend.app.contracts.ocr import (
    HandwritingAssessment,
    OcrRecognitionMethod,
    OcrRecognitionStatus,
    OcrSourceMode,
    PixelBoundingBox,
    PixelPolygon,
    PreprocessingVariant,
    PrintedOcrLine,
    PrintedOcrWord,
    WordGeometrySource,
    WordScoreSource,
)

logger = logging.getLogger("veridemand.routing.materialise_embedded")


@dataclass(slots=True)
class MaterialiseStats:
    """Privacy-safe aggregate counts for verified embedded materialisation."""

    candidate_words: int = 0
    verified_words: int = 0
    rejected_words: int = 0
    verified_lines: int = 0
    geometry_rejections: int = 0


@dataclass(slots=True)
class MaterialisedEmbeddedResult:
    """Public words/lines derived from verified embedded candidates."""

    words: list[PrintedOcrWord]
    lines: list[PrintedOcrLine]
    stats: MaterialiseStats


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _validate_bbox(bbox: NormalisedBoundingBox) -> NormalisedBoundingBox | None:
    try:
        width = bbox.width
        height = bbox.height
        x = _clamp01(bbox.x)
        y = _clamp01(bbox.y)
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        if not math.isfinite(width) or not math.isfinite(height):
            return None
        if width <= 0.0 or height <= 0.0:
            return None
        if x + width > 1.0 + 1e-9:
            width = 1.0 - x
        if y + height > 1.0 + 1e-9:
            height = 1.0 - y
        if width <= 1e-9 or height <= 1e-9:
            return None
        return NormalisedBoundingBox(x=x, y=y, width=width, height=height)
    except (ValueError, TypeError):
        return None


def _bbox_polygon(bbox: NormalisedBoundingBox) -> NormalisedPolygon:
    right = min(bbox.x + bbox.width, 1.0)
    bottom = min(bbox.y + bbox.height, 1.0)
    return NormalisedPolygon(
        points=[
            NormalisedPoint(x=bbox.x, y=bbox.y),
            NormalisedPoint(x=right, y=bbox.y),
            NormalisedPoint(x=right, y=bottom),
            NormalisedPoint(x=bbox.x, y=bottom),
        ]
    )


def _pixel_from_bbox(
    bbox: NormalisedBoundingBox,
    *,
    width_px: int,
    height_px: int,
) -> tuple[PixelBoundingBox, PixelPolygon]:
    x = max(0.0, bbox.x * width_px)
    y = max(0.0, bbox.y * height_px)
    w = max(1.0, bbox.width * width_px)
    h = max(1.0, bbox.height * height_px)
    if x + w > width_px:
        w = max(1.0, float(width_px) - x)
    if y + h > height_px:
        h = max(1.0, float(height_px) - y)
    pixel_bbox = PixelBoundingBox(x=x, y=y, width=w, height=h)
    pixel_polygon = PixelPolygon(
        points=[
            (x, y),
            (x + w, y),
            (x + w, y + h),
            (x, y + h),
        ]
    )
    return pixel_bbox, pixel_polygon


def _same_line(a: NormalisedBoundingBox, b: NormalisedBoundingBox) -> bool:
    """Provisional same-line rule: vertical centres close and horizontal overlap or gap small."""

    ay = a.y + a.height / 2.0
    by = b.y + b.height / 2.0
    median_h = max((a.height + b.height) / 2.0, 1e-4)
    if abs(ay - by) > median_h * 0.65:
        return False
    a_right = a.x + a.width
    b_right = b.x + b.width
    gap = max(0.0, max(a.x, b.x) - min(a_right, b_right))
    return gap <= max(a.width, b.width) * 0.75 + 0.02


def _union_bbox(boxes: list[NormalisedBoundingBox]) -> NormalisedBoundingBox:
    left = min(b.x for b in boxes)
    top = min(b.y for b in boxes)
    right = max(b.x + b.width for b in boxes)
    bottom = max(b.y + b.height for b in boxes)
    width = max(right - left, 1e-9)
    height = max(bottom - top, 1e-9)
    if left + width > 1.0:
        width = 1.0 - left
    if top + height > 1.0:
        height = 1.0 - top
    return NormalisedBoundingBox(x=left, y=top, width=max(width, 1e-9), height=max(height, 1e-9))


def group_verified_words_into_lines(
    words: list[tuple[NativeWord, NormalisedBoundingBox]],
    *,
    page_number: int,
    width_px: int,
    height_px: int,
    agreement_score: float,
) -> tuple[list[PrintedOcrLine], list[PrintedOcrWord]]:
    """Group verified native words into provisional lines and public OCR shapes."""

    ordered = sorted(words, key=lambda item: (item[1].y, item[1].x, item[0].id))
    clusters: list[list[tuple[NativeWord, NormalisedBoundingBox]]] = []
    for item in ordered:
        if not clusters:
            clusters.append([item])
            continue
        last = clusters[-1][-1][1]
        if _same_line(last, item[1]):
            clusters[-1].append(item)
        else:
            clusters.append([item])

    lines: list[PrintedOcrLine] = []
    public_words: list[PrintedOcrWord] = []
    word_seq = 0
    score = max(0.0, min(1.0, agreement_score if agreement_score > 0 else 0.85))

    for line_index, cluster in enumerate(clusters):
        cluster = sorted(cluster, key=lambda item: (item[1].x, item[0].id))
        line_bbox = _union_bbox([bbox for _, bbox in cluster])
        line_polygon = _bbox_polygon(line_bbox)
        line_pixel_bbox, line_pixel_polygon = _pixel_from_bbox(
            line_bbox, width_px=width_px, height_px=height_px
        )
        line_id = f"ocrline_p{page_number:04d}_{line_index + 1:06d}"
        texts = [w.normalised_text or w.text for w, _ in cluster]
        joined = unicodedata.normalize("NFC", " ".join(texts))
        if not joined.strip():
            continue
        source_ids = [w.id for w, _ in cluster]
        lines.append(
            PrintedOcrLine(
                id=line_id,
                page_number=page_number,
                sequence_index=line_index,
                text=joined,
                normalised_text=joined,
                detection_score=score,
                recognition_score=score,
                recognition_status=OcrRecognitionStatus.ACCEPTED,
                polygon=line_polygon,
                bbox=line_bbox,
                geometry=Geometry(polygon=line_polygon, bbox=line_bbox),
                pixel_polygon=line_pixel_polygon,
                pixel_bbox=line_pixel_bbox,
                preprocessing_variant=PreprocessingVariant.ORIGINAL_RGB,
                recognition_method=OcrRecognitionMethod.EMBEDDED_OCR_VERIFIED,
                source_mode=OcrSourceMode.EMBEDDED_OCR_AUTHORITY,
                handwriting_assessment=HandwritingAssessment.PENDING_PHASE_5,
                source_native_word_ids=source_ids,
            )
        )
        for native_word, bbox in cluster:
            word_seq += 1
            polygon = _bbox_polygon(bbox)
            pixel_bbox, pixel_polygon = _pixel_from_bbox(
                bbox, width_px=width_px, height_px=height_px
            )
            text = unicodedata.normalize("NFC", native_word.normalised_text or native_word.text)
            if not text:
                continue
            public_words.append(
                PrintedOcrWord(
                    id=f"ocrword_p{page_number:04d}_{word_seq:06d}",
                    page_number=page_number,
                    line_id=line_id,
                    sequence_index=word_seq - 1,
                    text=text,
                    normalised_text=text,
                    recognition_score=score,
                    score_source=WordScoreSource.EMBEDDED_VERIFICATION,
                    polygon=polygon,
                    bbox=bbox,
                    geometry=Geometry(polygon=polygon, bbox=bbox),
                    pixel_polygon=pixel_polygon,
                    pixel_bbox=pixel_bbox,
                    geometry_source=WordGeometrySource.EMBEDDED_NATIVE_BOX,
                    geometry_precision="embedded",
                    recognition_method=OcrRecognitionMethod.EMBEDDED_OCR_VERIFIED,
                    recognition_status=OcrRecognitionStatus.ACCEPTED,
                    handwriting_assessment=HandwritingAssessment.PENDING_PHASE_5,
                    source_mode=OcrSourceMode.EMBEDDED_OCR_AUTHORITY,
                    source_native_word_id=native_word.id,
                )
            )
    return lines, public_words


def materialise_verified_embedded_words(
    candidates: list[NativeWord],
    *,
    page_number: int,
    passed_word_ids: set[str] | None,
    failed_sample_indices: list[int] | None,
    sampled_words: list[NativeWord] | None,
    agreement_score: float,
    width_px: int,
    height_px: int,
) -> MaterialisedEmbeddedResult:
    """Select only verified candidates and build public embedded OCR output.

    When ``passed_word_ids`` is provided, only those ids are materialised.
    Otherwise, when sampled failure indices are provided, all candidates except
    sampled failures are kept (page-level pass with per-sample exclusions).
    When neither is provided (visual-only page pass), all geometrically valid
    candidates are materialised — callers must still enforce non-empty output
    and coverage gates before granting authority.
    """

    stats = MaterialiseStats(candidate_words=len(candidates))
    rejected_ids: set[str] = set()
    if sampled_words and failed_sample_indices:
        for idx in failed_sample_indices:
            if 0 <= idx < len(sampled_words):
                rejected_ids.add(sampled_words[idx].id)

    verified: list[tuple[NativeWord, NormalisedBoundingBox]] = []
    for word in candidates:
        if passed_word_ids is not None and word.id not in passed_word_ids:
            stats.rejected_words += 1
            continue
        if word.id in rejected_ids:
            stats.rejected_words += 1
            continue
        try:
            bbox = _validate_bbox(word.geometry.bbox)
        except Exception:
            bbox = None
        if bbox is None:
            stats.geometry_rejections += 1
            stats.rejected_words += 1
            continue
        verified.append((word, bbox))

    lines, public_words = group_verified_words_into_lines(
        verified,
        page_number=page_number,
        width_px=max(1, width_px),
        height_px=max(1, height_px),
        agreement_score=agreement_score,
    )
    stats.verified_words = len(public_words)
    stats.verified_lines = len(lines)
    logger.info(
        "materialise_embedded page=%s candidate_words=%s verified_words=%s "
        "rejected_words=%s verified_lines=%s geometry_rejections=%s",
        page_number,
        stats.candidate_words,
        stats.verified_words,
        stats.rejected_words,
        stats.verified_lines,
        stats.geometry_rejections,
    )
    return MaterialisedEmbeddedResult(words=public_words, lines=lines, stats=stats)


def nonblank_requires_usable_embedded_output(
    *,
    page_appears_blank: bool,
    verified_word_count: int,
    verified_line_count: int,
) -> bool:
    """Central invariant: nonblank + zero usable embedded output cannot be terminal."""

    if page_appears_blank:
        return False
    return verified_word_count < 1 and verified_line_count < 1

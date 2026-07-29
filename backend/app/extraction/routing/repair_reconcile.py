"""Retained-word protection and spatial reconciliation for targeted repair."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

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
from backend.app.contracts.repair import (
    RepairMethod,
    RepairRegionRecord,
    TargetedRepairPageSummary,
    WordProvenanceKind,
    WordRetentionClass,
)


@dataclass(slots=True)
class ClassifiedBaseWord:
    word: NativeWord
    retention: WordRetentionClass
    bbox: NormalisedBoundingBox


@dataclass(slots=True)
class RepairedWordCandidate:
    text: str
    recognition_score: float
    polygon: NormalisedPolygon
    bbox: NormalisedBoundingBox
    geometry: Geometry
    pixel_polygon: PixelPolygon
    pixel_bbox: PixelBoundingBox
    method: RepairMethod
    repair_region_id: str
    handwriting_assessment: HandwritingAssessment = HandwritingAssessment.PENDING_PHASE_5


@dataclass(slots=True)
class ReconcileResult:
    words: list[PrintedOcrWord]
    lines: list[PrintedOcrLine]
    summary: TargetedRepairPageSummary
    suppressed_source_ids: list[str] = field(default_factory=list)
    retained_source_ids: list[str] = field(default_factory=list)


def _overlap_ratio(a: NormalisedBoundingBox, b: NormalisedBoundingBox) -> float:
    ax1, ay1 = a.x + a.width, a.y + a.height
    bx1, by1 = b.x + b.width, b.y + b.height
    ix0, iy0 = max(a.x, b.x), max(a.y, b.y)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(1e-12, a.width * a.height)
    return inter / area_a


def _same_line(a: NormalisedBoundingBox, b: NormalisedBoundingBox) -> bool:
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
    pixel_polygon = PixelPolygon(points=[(x, y), (x + w, y), (x + w, y + h), (x, y + h)])
    return pixel_bbox, pixel_polygon


def classify_base_words(
    words: Sequence[NativeWord],
    *,
    failed_indices: Sequence[int],
    regions: Sequence[RepairRegionRecord],
    overlap_threshold: float = 0.35,
) -> list[ClassifiedBaseWord]:
    """Classify each base word for retention / suppression."""

    failed = set(failed_indices)
    classified: list[ClassifiedBaseWord] = []
    for i, word in enumerate(words):
        if word.geometry is None:
            classified.append(
                ClassifiedBaseWord(
                    word=word,
                    retention=WordRetentionClass.QUARANTINED,
                    bbox=NormalisedBoundingBox(x=0.0, y=0.0, width=1e-3, height=1e-3),
                )
            )
            continue
        bbox = word.geometry.bbox
        if i in failed:
            classified.append(
                ClassifiedBaseWord(
                    word=word, retention=WordRetentionClass.SUPPRESSED_FOR_REPAIR, bbox=bbox
                )
            )
            continue
        overlaps = False
        for region in regions:
            if _overlap_ratio(bbox, region.expanded_normalised_bbox) >= overlap_threshold:
                overlaps = True
                break
        if overlaps:
            classified.append(
                ClassifiedBaseWord(
                    word=word, retention=WordRetentionClass.OVERLAPS_REPAIR_REGION, bbox=bbox
                )
            )
        else:
            classified.append(
                ClassifiedBaseWord(word=word, retention=WordRetentionClass.RETAINED, bbox=bbox)
            )
    # Mark retained that are truly unaffected.
    for item in classified:
        if item.retention is WordRetentionClass.RETAINED:
            item.retention = WordRetentionClass.UNAFFECTED
            item.retention = WordRetentionClass.RETAINED  # public retained alias
    return classified


def _provenance_for_method(method: RepairMethod) -> WordProvenanceKind:
    if method is RepairMethod.LOCAL_DETECTION_AND_RECOGNITION:
        return WordProvenanceKind.TARGETED_REPAIR_LOCAL_OCR_WORD
    return WordProvenanceKind.TARGETED_REPAIR_RECOGNITION_WORD


def reconcile_repaired_page(
    *,
    page_number: int,
    classified: Sequence[ClassifiedBaseWord],
    repaired: Sequence[RepairedWordCandidate],
    regions: Sequence[RepairRegionRecord],
    width_px: int,
    height_px: int,
    agreement_score: float = 0.85,
) -> ReconcileResult:
    """Spatially reconcile retained base words with repaired region output."""

    retained: list[tuple[NativeWord, NormalisedBoundingBox]] = []
    suppressed_ids: list[str] = []
    for item in classified:
        if item.retention in {
            WordRetentionClass.SUPPRESSED_FOR_REPAIR,
            WordRetentionClass.OVERLAPS_REPAIR_REGION,
        }:
            suppressed_ids.append(item.word.id)
            continue
        if item.retention in {WordRetentionClass.RETAINED, WordRetentionClass.UNAFFECTED}:
            retained.append((item.word, item.bbox))

    # Drop repaired words that fall outside all repair regions or collide with retained.
    accepted_repaired: list[RepairedWordCandidate] = []
    for cand in repaired:
        text = unicodedata.normalize("NFC", cand.text or "").strip()
        if not text:
            continue
        if not math.isfinite(cand.recognition_score):
            continue
        inside = any(_overlap_ratio(cand.bbox, r.expanded_normalised_bbox) >= 0.15 for r in regions)
        if not inside:
            continue
        collides = any(_overlap_ratio(cand.bbox, rb) >= 0.55 for _, rb in retained)
        if collides:
            continue
        # Prefer repaired inside regions — skip near-duplicate repaired pairs.
        dup = any(
            _overlap_ratio(cand.bbox, other.bbox) >= 0.7
            and cand.text.strip().casefold() == other.text.strip().casefold()
            for other in accepted_repaired
        )
        if dup:
            continue
        accepted_repaired.append(cand)

    # Build combined provisional line groups by spatial order.
    combined: list[tuple[str, NormalisedBoundingBox, object]] = []
    for native, bbox in retained:
        combined.append(("retained", bbox, native))
    for cand in accepted_repaired:
        combined.append(("repaired", cand.bbox, cand))
    combined.sort(key=lambda t: (t[1].y, t[1].x))

    clusters: list[list[tuple[str, NormalisedBoundingBox, object]]] = []
    for entry in combined:
        if not clusters:
            clusters.append([entry])
            continue
        last = clusters[-1][-1][1]
        if _same_line(last, entry[1]):
            clusters[-1].append(entry)
        else:
            clusters.append([entry])

    lines: list[PrintedOcrLine] = []
    words_out: list[PrintedOcrWord] = []
    word_seq = 0
    score = max(0.0, min(1.0, agreement_score if agreement_score > 0 else 0.85))
    retained_ids: list[str] = []

    for line_index, cluster in enumerate(clusters):
        cluster = sorted(cluster, key=lambda t: (t[1].x,))
        line_bbox = _union_bbox([bbox for _, bbox, _ in cluster])
        line_polygon = _bbox_polygon(line_bbox)
        line_pixel_bbox, line_pixel_polygon = _pixel_from_bbox(
            line_bbox, width_px=width_px, height_px=height_px
        )
        line_id = f"ocrline_p{page_number:04d}_{line_index + 1:06d}"
        texts: list[str] = []
        source_ids: list[str] = []
        for kind, bbox, payload in cluster:
            word_seq += 1
            if kind == "retained":
                native = payload  # type: ignore[assignment]
                assert isinstance(native, NativeWord)
                text = unicodedata.normalize("NFC", native.normalised_text or native.text)
                if not text:
                    word_seq -= 1
                    continue
                texts.append(text)
                source_ids.append(native.id)
                retained_ids.append(native.id)
                polygon = _bbox_polygon(bbox)
                pixel_bbox, pixel_polygon = _pixel_from_bbox(
                    bbox, width_px=width_px, height_px=height_px
                )
                words_out.append(
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
                        source_native_word_id=native.id,
                        provisional_class=None,
                    )
                )
            else:
                cand = payload  # type: ignore[assignment]
                assert isinstance(cand, RepairedWordCandidate)
                text = unicodedata.normalize("NFC", cand.text)
                texts.append(text)
                words_out.append(
                    PrintedOcrWord(
                        id=f"ocrword_p{page_number:04d}_{word_seq:06d}",
                        page_number=page_number,
                        line_id=line_id,
                        sequence_index=word_seq - 1,
                        text=text,
                        normalised_text=text,
                        recognition_score=max(0.0, min(1.0, cand.recognition_score)),
                        score_source=WordScoreSource.PADDLE_RECOGNITION,
                        polygon=cand.polygon,
                        bbox=cand.bbox,
                        geometry=cand.geometry,
                        pixel_polygon=cand.pixel_polygon,
                        pixel_bbox=cand.pixel_bbox,
                        geometry_source=WordGeometrySource.PADDLE_WORD_BOX
                        if cand.method is RepairMethod.LOCAL_DETECTION_AND_RECOGNITION
                        else WordGeometrySource.EMBEDDED_NATIVE_BOX,
                        geometry_precision="detector"
                        if cand.method is RepairMethod.LOCAL_DETECTION_AND_RECOGNITION
                        else "embedded",
                        recognition_method=OcrRecognitionMethod.PADDLEOCR_PRINTED,
                        recognition_status=(
                            OcrRecognitionStatus.ACCEPTED
                            if cand.recognition_score >= 0.5
                            else OcrRecognitionStatus.LOW_CONFIDENCE
                        ),
                        handwriting_assessment=cand.handwriting_assessment,
                        source_mode=OcrSourceMode.EMBEDDED_OCR_AUTHORITY,
                        source_native_word_id=None,
                    )
                )
        joined = unicodedata.normalize("NFC", " ".join(texts))
        if not joined.strip():
            continue
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

    repaired_count = sum(
        1 for w in words_out if w.recognition_method is OcrRecognitionMethod.PADDLEOCR_PRINTED
    )
    retained_count = len(words_out) - repaired_count
    page_method = None
    if accepted_repaired:
        page_method = accepted_repaired[0].method

    summary = TargetedRepairPageSummary(
        retained_native_words=0,
        retained_embedded_words=retained_count,
        repaired_words=repaired_count,
        suppressed_words=len(suppressed_ids),
        repair_regions=len(regions),
        repair_method=page_method,
    )
    return ReconcileResult(
        words=words_out,
        lines=lines,
        summary=summary,
        suppressed_source_ids=suppressed_ids,
        retained_source_ids=retained_ids,
    )


# Re-export for callers that need provenance labels in diagnostics.
__all__ = [
    "ClassifiedBaseWord",
    "ReconcileResult",
    "RepairedWordCandidate",
    "WordProvenanceKind",
    "_provenance_for_method",
    "classify_base_words",
    "reconcile_repaired_page",
]

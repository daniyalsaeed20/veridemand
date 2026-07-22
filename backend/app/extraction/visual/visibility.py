"""Native-text visibility probe against a low-DPI rendered page.

Never logs native or OCR text. Uses Pillow/NumPy only (no OpenCV).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from backend.app.contracts.native import NativePageResult, NativeWord
from backend.app.contracts.visual import (
    NativeVisibilityDecision,
    NativeVisibilityResult,
    VisualAgreementStatusPhase4,
)
from backend.app.contracts.warnings import NativeReasonCode
from backend.app.extraction.visual.renderer import flatten_to_rgb
from PIL import Image

logger = logging.getLogger("veridemand.visual.visibility")


@dataclass(frozen=True, slots=True)
class VisibilityThresholds:
    """Configurable visibility probe thresholds."""

    min_words: int
    min_visible_word_ratio: float
    min_region_variance: float
    min_edge_density: float


@dataclass(frozen=True, slots=True)
class _WordVisibility:
    visible: bool
    blank_like: bool
    variance: float
    edge_density: float
    contrast: float


def _sample_word_region(
    gray: np.ndarray,
    word: NativeWord,
) -> _WordVisibility | None:
    height, width = gray.shape[:2]
    bbox = word.geometry.bbox
    x0 = int(max(0, math_floor(bbox.x * width)))
    y0 = int(max(0, math_floor(bbox.y * height)))
    x1 = int(min(width, math_ceil((bbox.x + bbox.width) * width)))
    y1 = int(min(height, math_ceil((bbox.y + bbox.height) * height)))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None

    region = gray[y0:y1, x0:x1].astype(np.float32)
    variance = float(region.var())
    gx = np.abs(np.diff(region, axis=1)).mean() if region.shape[1] > 1 else 0.0
    gy = np.abs(np.diff(region, axis=0)).mean() if region.shape[0] > 1 else 0.0
    edge_density = float((gx + gy) / 255.0)

    pad = 2
    rx0 = max(0, x0 - pad)
    ry0 = max(0, y0 - pad)
    rx1 = min(width, x1 + pad)
    ry1 = min(height, y1 + pad)
    surround = gray[ry0:ry1, rx0:rx1].astype(np.float32)
    contrast = abs(float(region.mean()) - float(surround.mean()))

    return _WordVisibility(
        visible=False,
        blank_like=False,
        variance=variance,
        edge_density=edge_density,
        contrast=contrast,
    )


def math_floor(value: float) -> int:
    import math

    return math.floor(value)


def math_ceil(value: float) -> int:
    import math

    return math.ceil(value)


def probe_native_visibility(
    image: Image.Image,
    page: NativePageResult,
    *,
    thresholds: VisibilityThresholds,
) -> NativeVisibilityResult:
    """Evaluate whether accepted native words appear as visible ink."""

    words = list(page.words)
    if len(words) < thresholds.min_words:
        return NativeVisibilityResult(
            visual_agreement_status=VisualAgreementStatusPhase4.EVALUATED_PHASE_4_VISIBILITY,
            native_visibility_score=None,
            native_visible_word_ratio=None,
            native_blank_like_word_ratio=None,
            sampled_word_count=len(words),
            native_visibility_decision=NativeVisibilityDecision.INSUFFICIENT_WORDS,
            reason_codes=[NativeReasonCode.NATIVE_TEXT_VISIBILITY_UNCERTAIN.value],
            downgraded=False,
        )

    rgb = flatten_to_rgb(image)
    gray = np.asarray(rgb.convert("L"), dtype=np.float32)

    visible = 0
    blank_like = 0
    sampled = 0
    for word in words:
        sample = _sample_word_region(gray, word)
        if sample is None:
            continue
        sampled += 1
        is_visible = sample.variance >= thresholds.min_region_variance and (
            sample.edge_density >= thresholds.min_edge_density
            or sample.contrast >= thresholds.min_region_variance
        )
        if is_visible:
            visible += 1
        else:
            blank_like += 1

    if sampled < thresholds.min_words:
        return NativeVisibilityResult(
            visual_agreement_status=VisualAgreementStatusPhase4.EVALUATED_PHASE_4_VISIBILITY,
            native_visibility_score=None,
            native_visible_word_ratio=None,
            native_blank_like_word_ratio=None,
            sampled_word_count=sampled,
            native_visibility_decision=NativeVisibilityDecision.INSUFFICIENT_WORDS,
            reason_codes=[NativeReasonCode.NATIVE_TEXT_VISIBILITY_UNCERTAIN.value],
            downgraded=False,
        )

    visible_ratio = visible / sampled
    blank_ratio = blank_like / sampled
    score = max(0.0, min(1.0, visible_ratio))

    if visible_ratio >= thresholds.min_visible_word_ratio:
        decision = NativeVisibilityDecision.NATIVE_TEXT_VISUALLY_SUPPORTED
        reason = NativeReasonCode.NATIVE_TEXT_VISUALLY_SUPPORTED.value
        downgraded = False
    elif blank_ratio >= (1.0 - thresholds.min_visible_word_ratio):
        decision = NativeVisibilityDecision.NATIVE_TEXT_NOT_VISUALLY_PRESENT
        reason = NativeReasonCode.NATIVE_TEXT_NOT_VISUALLY_PRESENT.value
        downgraded = True
    else:
        decision = NativeVisibilityDecision.NATIVE_TEXT_VISIBILITY_UNCERTAIN
        reason = NativeReasonCode.NATIVE_TEXT_VISIBILITY_UNCERTAIN.value
        # Conservative: uncertain visibility routes to visual OCR.
        downgraded = True

    logger.info(
        "Native visibility probe complete",
        extra={
            "page_number": page.page_number,
            "sampled_word_count": sampled,
            "visible_word_ratio": round(visible_ratio, 4),
            "blank_like_word_ratio": round(blank_ratio, 4),
            "decision": decision.value,
            "downgraded": downgraded,
        },
    )

    return NativeVisibilityResult(
        visual_agreement_status=VisualAgreementStatusPhase4.EVALUATED_PHASE_4_VISIBILITY,
        native_visibility_score=score,
        native_visible_word_ratio=visible_ratio,
        native_blank_like_word_ratio=blank_ratio,
        sampled_word_count=sampled,
        native_visibility_decision=decision,
        reason_codes=[reason],
        downgraded=downgraded,
    )

"""Low-cost embedded OCR visual-agreement evaluation."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

import numpy as np
from backend.app.contracts.native import NativePageResult, NativeWord
from backend.app.extraction.routing.models import RoutingPolicy, VisualAgreementMetrics
from PIL import Image


def _region_code(word: NativeWord) -> str:
    bbox = word.geometry.bbox
    cx = bbox.x + bbox.width / 2.0
    cy = bbox.y + bbox.height / 2.0
    col = "L" if cx < 0.33 else ("R" if cx > 0.66 else "C")
    row = "T" if cy < 0.33 else ("B" if cy > 0.66 else "M")
    return f"{row}{col}"


def _word_priority(word: NativeWord) -> tuple[int, int, str]:
    """Prefer longer tokens, dates/numerics, then stable id for determinism."""

    text = word.normalised_text or word.text or ""
    has_digit = 1 if any(ch.isdigit() for ch in text) else 0
    return (-len(text), -has_digit, word.id)


def sample_words_for_agreement(
    words: Sequence[NativeWord],
    *,
    sample_size: int,
    page_number: int,
) -> list[NativeWord]:
    """Deterministic stratified sample across page regions."""

    if not words or sample_size <= 0:
        return []
    buckets: dict[str, list[NativeWord]] = {}
    for word in words:
        buckets.setdefault(_region_code(word), []).append(word)
    for key in buckets:
        buckets[key] = sorted(buckets[key], key=_word_priority)

    # Stable shuffle seed from page number + sample size (no text).
    seed_bytes = hashlib.sha256(f"p{page_number}:n{sample_size}:v1".encode()).digest()
    seed = int.from_bytes(seed_bytes[:8], "big")

    selected: list[NativeWord] = []
    region_keys = sorted(buckets.keys())
    # Round-robin from each region.
    indices = {k: 0 for k in region_keys}
    while len(selected) < sample_size and region_keys:
        progressed = False
        for key in list(region_keys):
            bucket = buckets[key]
            idx = indices[key]
            if idx >= len(bucket):
                region_keys.remove(key)
                continue
            selected.append(bucket[idx])
            indices[key] = idx + 1
            progressed = True
            if len(selected) >= sample_size:
                break
        if not progressed:
            break

    # Deterministic order by geometry then id.
    selected.sort(key=lambda w: (w.geometry.bbox.y, w.geometry.bbox.x, w.id))
    # Use seed only to break ties in excess candidates (already stratified).
    _ = seed
    return selected[:sample_size]


def _probe_box(
    gray: np.ndarray,
    word: NativeWord,
    *,
    min_variance: float,
    min_edge_density: float,
) -> tuple[bool, bool, bool, float, float, float]:
    """Return (in_bounds, visible, blank_like, variance, edge, contrast)."""

    height, width = gray.shape[:2]
    bbox = word.geometry.bbox
    x0 = int(max(0, math.floor(bbox.x * width)))
    y0 = int(max(0, math.floor(bbox.y * height)))
    x1 = int(min(width, math.ceil((bbox.x + bbox.width) * width)))
    y1 = int(min(height, math.ceil((bbox.y + bbox.height) * height)))
    if x1 <= x0 or y1 <= y0:
        return False, False, True, 0.0, 0.0, 0.0
    if (
        bbox.x < -0.01
        or bbox.y < -0.01
        or bbox.x + bbox.width > 1.01
        or bbox.y + bbox.height > 1.01
    ):
        in_bounds = False
    else:
        in_bounds = True
    if x1 - x0 < 2 or y1 - y0 < 2:
        return in_bounds, False, True, 0.0, 0.0, 0.0

    region = gray[y0:y1, x0:x1].astype(np.float32)
    variance = float(region.var())
    mean_luma = float(region.mean())
    gx = np.abs(np.diff(region, axis=1)).mean() if region.shape[1] > 1 else 0.0
    gy = np.abs(np.diff(region, axis=0)).mean() if region.shape[0] > 1 else 0.0
    edge_density = float((gx + gy) / 255.0)
    pad = 2
    surround = gray[
        max(0, y0 - pad) : min(height, y1 + pad),
        max(0, x0 - pad) : min(width, x1 + pad),
    ].astype(np.float32)
    contrast = abs(mean_luma - float(surround.mean()))
    blank_like = mean_luma >= 245.0 and contrast < 8.0 and edge_density < 0.02
    visible = (
        in_bounds
        and not blank_like
        and variance >= min_variance
        and edge_density >= min_edge_density
    )
    return in_bounds, visible, blank_like, variance, edge_density, contrast


def evaluate_visual_agreement(
    image: Image.Image,
    page: NativePageResult,
    policy: RoutingPolicy,
    *,
    min_region_variance: float = 4.0,
    min_edge_density: float = 0.01,
) -> VisualAgreementMetrics:
    """Compare native word boxes against a low-resolution page render."""

    words = list(page.words or [])
    sampled = sample_words_for_agreement(
        words, sample_size=policy.visual_sample_size, page_number=page.page_number
    )
    if not sampled:
        return VisualAgreementMetrics(
            reason_codes=["insufficient_boxes_for_visual_agreement"],
        )

    gray = np.asarray(image.convert("L"), dtype=np.float32)
    visible = 0
    blank = 0
    oob = 0
    vars_: list[float] = []
    edges: list[float] = []
    contrasts: list[float] = []
    failed: list[int] = []
    covered_regions: set[str] = set()

    for idx, word in enumerate(sampled):
        covered_regions.add(_region_code(word))
        in_bounds, is_visible, blank_like, variance, edge, contrast = _probe_box(
            gray,
            word,
            min_variance=min_region_variance,
            min_edge_density=min_edge_density,
        )
        vars_.append(variance)
        edges.append(edge)
        contrasts.append(contrast)
        if not in_bounds:
            oob += 1
            failed.append(idx)
        elif blank_like or not is_visible:
            blank += 1 if blank_like else 0
            failed.append(idx)
        else:
            visible += 1

    n = len(sampled)
    visible_ratio = visible / n
    blank_ratio = blank / n
    oob_ratio = oob / n
    spatial = len(covered_regions) / max(1, min(9, n))
    # Composite score weights visibility heavily; penalise OOB and blank boxes.
    score = max(
        0.0,
        min(
            1.0,
            0.70 * visible_ratio
            + 0.15 * spatial
            + 0.15 * (1.0 - min(1.0, blank_ratio + oob_ratio)),
        ),
    )
    reasons: list[str] = []
    if visible_ratio < policy.min_visible_box_ratio:
        reasons.append("low_visible_box_ratio")
    if oob_ratio > 0.15:
        reasons.append("high_out_of_bounds_ratio")
    if blank_ratio > 0.30:
        reasons.append("high_blank_box_ratio")
    if score < policy.min_visual_agreement:
        reasons.append("visual_agreement_below_threshold")
    else:
        reasons.append("visual_agreement_passed")

    return VisualAgreementMetrics(
        sampled_box_count=n,
        visible_box_ratio=visible_ratio,
        blank_box_ratio=blank_ratio,
        out_of_bounds_ratio=oob_ratio,
        mean_variance=float(sum(vars_) / n) if vars_ else 0.0,
        mean_edge_density=float(sum(edges) / n) if edges else 0.0,
        mean_contrast=float(sum(contrasts) / n) if contrasts else 0.0,
        spatial_coverage=spatial,
        visual_agreement_score=score,
        failed_box_indices=failed,
        reason_codes=reasons,
    )

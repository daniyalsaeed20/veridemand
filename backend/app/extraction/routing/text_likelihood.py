"""Cheap text-likelihood / blank-page preflight (no OCR)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from backend.app.extraction.routing.models import RoutingPolicy
from PIL import Image


@dataclass(frozen=True, slots=True)
class TextLikelihoodResult:
    """Thumbnail-based content estimate."""

    ink_density: float
    edge_density: float
    variance: float
    appears_blank: bool
    reason_codes: tuple[str, ...]


def evaluate_text_likelihood(
    image: Image.Image,
    policy: RoutingPolicy,
) -> TextLikelihoodResult:
    """Measure ink/edge density on a grayscale thumbnail.

    Conservative: only mark blank when all gates pass. Sparse content
    (notes, plates, dates, handwriting) must NOT be skipped.
    """

    rgb = image.convert("RGB")
    # Downscale for cost; keep enough resolution for sparse ink.
    max_side = 384
    w, h = rgb.size
    scale = min(1.0, max_side / float(max(w, h)))
    if scale < 1.0:
        rgb = rgb.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.Resampling.BILINEAR,
        )
    gray = np.asarray(rgb.convert("L"), dtype=np.float32)
    variance = float(gray.var())
    # Ink: pixels darker than near-white background.
    ink_mask = gray < 240.0
    ink_density = float(ink_mask.mean())
    gx = np.abs(np.diff(gray, axis=1)).mean() if gray.shape[1] > 1 else 0.0
    gy = np.abs(np.diff(gray, axis=0)).mean() if gray.shape[0] > 1 else 0.0
    edge_density = float((gx + gy) / 255.0)

    reasons: list[str] = []
    appears_blank = (
        ink_density <= policy.blank_max_ink_density
        and edge_density <= policy.blank_max_edge_density
        and variance <= policy.blank_max_variance
    )
    if appears_blank:
        reasons.append("blank_page_preflight")
    else:
        if ink_density > policy.blank_max_ink_density:
            reasons.append("ink_present")
        if edge_density > policy.blank_max_edge_density:
            reasons.append("edges_present")
        if variance > policy.blank_max_variance:
            reasons.append("variance_present")

    return TextLikelihoodResult(
        ink_density=ink_density,
        edge_density=edge_density,
        variance=variance,
        appears_blank=appears_blank,
        reason_codes=tuple(reasons),
    )

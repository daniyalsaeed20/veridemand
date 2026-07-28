"""Generic embedded-layer coverage gate for form-like scanned pages.

Metrics are privacy-safe aggregates only (no text). Used to decide whether an
embedded OCR layer represents enough of the visible printed page to be
authoritative. Handwriting is never classified here — only flagged as
pending Phase 5 when image-only ink is likely outside candidate boxes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from backend.app.contracts.native import NativeWord
from backend.app.extraction.routing.models import RoutingPolicy
from PIL import Image


@dataclass(slots=True)
class EmbeddedCoverageMetrics:
    """Privacy-safe coverage diagnostics for embedded OCR authority."""

    candidate_box_coverage: float = 0.0
    form_line_density: float = 0.0
    checkbox_density: float = 0.0
    visible_ink_density: float = 0.0
    ink_outside_candidates_ratio: float = 0.0
    uncovered_textlike_ratio: float = 0.0
    handwriting_pending_phase_5: bool = False
    adequate: bool = False
    reason_codes: list[str] = field(default_factory=list)


def _candidate_mask(
    words: list[NativeWord],
    *,
    height: int,
    width: int,
) -> np.ndarray:
    mask = np.zeros((height, width), dtype=bool)
    for word in words:
        bbox = word.geometry.bbox
        x0 = int(max(0, math.floor(bbox.x * width)))
        y0 = int(max(0, math.floor(bbox.y * height)))
        x1 = int(min(width, math.ceil((bbox.x + bbox.width) * width)))
        y1 = int(min(height, math.ceil((bbox.y + bbox.height) * height)))
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = True
    return mask


def _form_line_density(gray: np.ndarray) -> float:
    """Estimate ruled-form / grid density via strong horizontal edges."""

    # Horizontal rules produce vertical gradients (diff along rows / axis=0).
    gy = np.abs(np.diff(gray.astype(np.float32), axis=0))
    row_hits = (gy > 25.0).mean(axis=1)
    return float(min(1.0, (row_hits > 0.05).mean()))


def _checkbox_density(gray: np.ndarray) -> float:
    """Rough checkbox-like mark density via local high-edge square patches."""

    h, w = gray.shape
    if h < 32 or w < 32:
        return 0.0
    # Downsample for speed.
    step_y = max(8, h // 64)
    step_x = max(8, w // 64)
    hits = 0
    probes = 0
    for y in range(0, h - 16, step_y):
        for x in range(0, w - 16, step_x):
            probes += 1
            patch = gray[y : y + 16, x : x + 16].astype(np.float32)
            edge = float(
                (np.abs(np.diff(patch, axis=0)).mean() + np.abs(np.diff(patch, axis=1)).mean())
                / 255.0
            )
            contrast = float(patch.max() - patch.min())
            if edge >= 0.08 and contrast >= 40.0:
                # Square-ish dark rim heuristic.
                border = np.concatenate(
                    [
                        patch[0, :],
                        patch[-1, :],
                        patch[:, 0],
                        patch[:, -1],
                    ]
                )
                if float(border.mean()) < float(patch[4:12, 4:12].mean()) - 8.0:
                    hits += 1
    if probes <= 0:
        return 0.0
    return float(min(1.0, hits / probes))


def evaluate_embedded_coverage(
    image: Image.Image,
    words: list[NativeWord],
    policy: RoutingPolicy,
) -> EmbeddedCoverageMetrics:
    """Decide whether candidate geometry covers enough of the visible page."""

    gray = np.asarray(image.convert("L"), dtype=np.float32)
    height, width = gray.shape[:2]
    page_area = max(1, height * width)
    ink = gray < 235.0
    ink_density = float(ink.mean())
    form_density = _form_line_density(gray)
    checkbox_density = _checkbox_density(gray)

    if not words:
        return EmbeddedCoverageMetrics(
            candidate_box_coverage=0.0,
            form_line_density=form_density,
            checkbox_density=checkbox_density,
            visible_ink_density=ink_density,
            ink_outside_candidates_ratio=1.0 if ink_density > 0 else 0.0,
            uncovered_textlike_ratio=1.0 if ink_density > policy.blank_max_ink_density else 0.0,
            handwriting_pending_phase_5=ink_density > policy.blank_max_ink_density * 4,
            adequate=False,
            reason_codes=["embedded_coverage_no_candidates"],
        )

    mask = _candidate_mask(words, height=height, width=width)
    candidate_coverage = float(mask.mean())
    ink_outside = ink & ~mask
    ink_outside_ratio = float(ink_outside.sum() / max(1, int(ink.sum())))
    # Text-like ink: darker than paper with local edge energy.
    gy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
    gx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
    edge = (gx + gy) / 255.0
    textlike = ink & (edge > 0.04)
    uncovered_textlike = textlike & ~mask
    uncovered_ratio = float(uncovered_textlike.sum() / max(1, int(textlike.sum())))

    # Informational only — do not classify handwriting.
    handwriting_pending = (
        form_density >= policy.min_form_line_density_for_coverage_gate
        and uncovered_ratio >= 0.25
        and ink_outside_ratio >= 0.20
    )

    reasons: list[str] = []
    adequate = True
    min_box = policy.min_candidate_box_coverage
    max_outside = policy.max_ink_outside_candidates_ratio
    max_uncovered = policy.max_uncovered_textlike_ratio
    form_like = form_density >= policy.min_form_line_density_for_coverage_gate or (
        checkbox_density >= policy.min_checkbox_density_for_coverage_gate
        and form_density >= policy.min_form_line_density_for_coverage_gate * 0.5
    )

    if form_like and candidate_coverage < min_box:
        adequate = False
        reasons.append("embedded_coverage_insufficient")
    if form_like and ink_outside_ratio > max_outside:
        adequate = False
        reasons.append("visible_ink_outside_candidates")
    if form_like and uncovered_ratio > max_uncovered:
        adequate = False
        reasons.append("uncovered_textlike_regions")
    if handwriting_pending:
        reasons.append("handwriting_pending_phase_5")
    if adequate:
        reasons.append("embedded_coverage_adequate")

    _ = page_area
    return EmbeddedCoverageMetrics(
        candidate_box_coverage=candidate_coverage,
        form_line_density=form_density,
        checkbox_density=checkbox_density,
        visible_ink_density=ink_density,
        ink_outside_candidates_ratio=ink_outside_ratio,
        uncovered_textlike_ratio=uncovered_ratio,
        handwriting_pending_phase_5=handwriting_pending,
        adequate=adequate,
        reason_codes=reasons,
    )

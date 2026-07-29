"""Conservative grid / ruling-line interference detection for printed OCR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class GridInterferenceResult:
    """Grid signals for quality evaluation and artefact filtering.

    ``grid_intersection_ratio`` — higher means more OCR boxes intersect ruling lines.
    Only line-only detections (no credible character evidence) are suppressible.
    """

    horizontal_line_density: float
    vertical_line_density: float
    grid_intersection_count: int
    grid_intersection_ratio: float
    line_only_detection_indices: tuple[int, ...]
    reason_codes: list[str]


def _poly_bbox(poly: list[tuple[float, float]]) -> tuple[float, float, float, float] | None:
    if not poly:
        return None
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def detect_grid_interference(
    image: Any,
    raw_lines: list[Any],
) -> GridInterferenceResult:
    """Detect ruling-line interference without destroying character-touching boxes."""

    width, height = 1, 1
    if image is not None and hasattr(image, "size"):
        width, height = int(image.size[0]), int(image.size[1])

    h_density = 0.0
    v_density = 0.0
    intersections = 0
    row_mask = None
    col_mask = None

    if np is not None and image is not None:
        gray = image.convert("L") if hasattr(image, "convert") else image
        arr = np.asarray(gray, dtype=np.uint8)
        dark = arr < 96
        row_frac = dark.mean(axis=1)
        col_frac = dark.mean(axis=0)
        row_mask = row_frac > 0.55
        col_mask = col_frac > 0.55
        long_h = int(np.sum(row_mask))
        long_v = int(np.sum(col_mask))
        h_density = long_h / max(1, height)
        v_density = long_v / max(1, width)
        intersections = int(min(long_h, long_v) * 0.35)

    intersecting = 0
    line_only: list[int] = []
    for idx, line in enumerate(raw_lines):
        poly = getattr(line, "polygon_px", None) or []
        bbox = _poly_bbox(poly)
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        w = max(1.0, x1 - x0)
        h = max(1.0, y1 - y0)
        aspect = max(w / h, h / w)
        text = str(getattr(line, "text", "") or "").strip()
        # Symbol/line-only: extremely elongated box with little alphanumeric content.
        alnum = sum(1 for ch in text if ch.isalnum())
        touches_grid = False
        if row_mask is not None and col_mask is not None and np is not None:
            y_mid = int(max(0, min(height - 1, (y0 + y1) / 2)))
            x_mid = int(max(0, min(width - 1, (x0 + x1) / 2)))
            # Box intersects a long ruling if its span overlaps a dense row/col.
            y0i = int(max(0, min(height - 1, y0)))
            y1i = int(max(0, min(height - 1, y1)))
            x0i = int(max(0, min(width - 1, x0)))
            x1i = int(max(0, min(width - 1, x1)))
            if np.any(row_mask[y0i : y1i + 1]) or np.any(col_mask[x0i : x1i + 1]):
                touches_grid = True
            # Centre on a ruling line is a stronger signal for line-only artefacts.
            if bool(row_mask[y_mid]) and h < max(3.0, height * 0.008) and aspect > 8:
                touches_grid = True
            if bool(col_mask[x_mid]) and w < max(3.0, width * 0.008) and aspect > 8:
                touches_grid = True
        if touches_grid:
            intersecting += 1
        if (aspect >= 12 and alnum == 0 and (not text or all(not ch.isalnum() for ch in text))) or (
            aspect >= 18 and len(text) <= 1
        ):
            line_only.append(idx)

    ratio = intersecting / max(1, len(raw_lines))
    reasons: list[str] = []
    if h_density > 0.03:
        reasons.append("horizontal_ruling_density")
    if v_density > 0.02:
        reasons.append("vertical_ruling_density")
    if ratio > 0.2:
        reasons.append("ocr_boxes_intersect_grid")
    if line_only:
        reasons.append("line_only_detections")

    return GridInterferenceResult(
        horizontal_line_density=float(h_density),
        vertical_line_density=float(v_density),
        grid_intersection_count=int(intersections),
        grid_intersection_ratio=float(min(1.0, ratio)),
        line_only_detection_indices=tuple(line_only),
        reason_codes=reasons,
    )


def is_suppressible_line_only(raw_line: Any, *, line_only_index: bool) -> bool:
    """Return True only for confidently line-only detections with no character evidence."""

    if not line_only_index:
        return False
    text = str(getattr(raw_line, "text", "") or "").strip()
    if any(ch.isalnum() for ch in text):
        return False
    score = float(getattr(raw_line, "recognition_score", 0.0) or 0.0)
    return score < 0.85 or len(text) <= 1

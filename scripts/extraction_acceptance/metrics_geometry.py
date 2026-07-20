"""Geometry metrics: polygon validity, IoU, alignment helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class GeometryMetrics:
    valid_polygon_rate: float
    out_of_bounds_polygon_rate: float
    centre_in_region_rate: float | None
    mean_iou: float | None
    rotation_correct: bool | None
    invalid_count: int
    oob_count: int
    total_polygons: int

    def as_dict(self) -> dict:
        return asdict(self)


def polygon_valid(poly: list[list[float]], *, eps: float = 1e-6) -> bool:
    if not isinstance(poly, list) or len(poly) < 3:
        return False
    xs: list[float] = []
    ys: list[float] = []
    for pt in poly:
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            return False
        x, y = float(pt[0]), float(pt[1])
        if any(v != v or v in (float("inf"), float("-inf")) for v in (x, y)):  # NaN/inf
            return False
        xs.append(x)
        ys.append(y)
    # non-zero area (simple shoelace)
    area = 0.0
    for i in range(len(xs)):
        j = (i + 1) % len(xs)
        area += xs[i] * ys[j] - xs[j] * ys[i]
    return abs(area) / 2.0 > eps


def polygon_oob(poly: list[list[float]], *, eps: float = 1e-6) -> bool:
    for pt in poly:
        x, y = float(pt[0]), float(pt[1])
        if x < -eps or x > 1.0 + eps or y < -eps or y > 1.0 + eps:
            return True
    return False


def bbox_from_polygon(poly: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def centroid(poly: list[list[float]]) -> tuple[float, float]:
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def iou_bbox(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def iou_polygons(a: list[list[float]], b: list[list[float]]) -> float:
    return iou_bbox(bbox_from_polygon(a), bbox_from_polygon(b))


def point_in_bbox(x: float, y: float, box: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = box
    return x0 <= x <= x1 and y0 <= y <= y1


def compute_geometry_metrics(
    polygons: list[list[list[float]]],
    *,
    expected_regions: list[tuple[float, float, float, float]] | None = None,
    paired_reference_polygons: list[list[list[float]]] | None = None,
    declared_rotation: int | None = None,
    expected_rotation: int | None = None,
) -> GeometryMetrics:
    total = len(polygons)
    if total == 0:
        return GeometryMetrics(1.0, 0.0, None, None, None, 0, 0, 0)
    invalid = sum(1 for p in polygons if not polygon_valid(p))
    oob = sum(1 for p in polygons if polygon_oob(p))
    centre_rate = None
    if expected_regions is not None and len(expected_regions) == total:
        hits = 0
        for poly, region in zip(polygons, expected_regions, strict=True):
            cx, cy = centroid(poly)
            if point_in_bbox(cx, cy, region):
                hits += 1
        centre_rate = hits / total
    mean_iou = None
    if paired_reference_polygons is not None and len(paired_reference_polygons) == total:
        ious = [
            iou_polygons(a, b)
            for a, b in zip(polygons, paired_reference_polygons, strict=True)
            if polygon_valid(a) and polygon_valid(b)
        ]
        mean_iou = sum(ious) / max(1, len(ious)) if ious else 0.0
    rot_ok = None
    if declared_rotation is not None and expected_rotation is not None:
        rot_ok = (declared_rotation % 360) == (expected_rotation % 360)
    return GeometryMetrics(
        valid_polygon_rate=(total - invalid) / total,
        out_of_bounds_polygon_rate=oob / total,
        centre_in_region_rate=centre_rate,
        mean_iou=mean_iou,
        rotation_correct=rot_ok,
        invalid_count=invalid,
        oob_count=oob,
        total_polygons=total,
    )

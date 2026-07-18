"""Polygon validation helpers for normalized page coordinates."""

from typing import Annotated

from pydantic import AfterValidator, Field

Point = tuple[float, float]
Polygon = list[Point]


def validate_normalized_polygon(points: list[tuple[float, float]]) -> None:
    if len(points) < 3:
        raise ValueError("polygon must have at least 3 points")
    for x, y in points:
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError("polygon coordinates must be in [0, 1]")


def normalize_polygon(
    points: list[tuple[float, float]], page_width: float, page_height: float
) -> list[tuple[float, float]]:
    if page_width <= 0 or page_height <= 0:
        raise ValueError("page dimensions must be positive")
    normalized = [(x / page_width, y / page_height) for x, y in points]
    validate_normalized_polygon(normalized)
    return normalized


def _check_polygon(points: list[list[float]]) -> list[list[float]]:
    tuples = [(float(p[0]), float(p[1])) for p in points if len(p) >= 2]
    validate_normalized_polygon(tuples)
    return [[x, y] for x, y in tuples]


NormalizedPolygon = Annotated[
    list[list[float]],
    AfterValidator(_check_polygon),
    Field(min_length=3),
]

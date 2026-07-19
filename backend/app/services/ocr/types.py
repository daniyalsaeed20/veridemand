"""Application-neutral OCR result types (no Paddle imports)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OcrDetection:
    """One detected text region from the OCR engine."""

    text: str
    confidence: float
    # Pixel-space polygon [[x,y], ...] origin top-left of the rendered image
    polygon_px: list[tuple[float, float]]


@dataclass
class OcrRawResult:
    """Neutral OCR pass output before coordinate normalization."""

    detections: list[OcrDetection] = field(default_factory=list)
    engine_name: str = "paddleocr"
    engine_version: str = "2.7.3"
    warnings: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0


@dataclass
class OcrAdapterMetrics:
    init_count: int = 0
    recognize_count: int = 0
    cancel_count: int = 0
    error_count: int = 0
    last_init_ms: float | None = None
    last_recognize_ms: float | None = None

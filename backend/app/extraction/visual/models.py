"""Internal models and runtime configuration for visual OCR."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class OcrRuntimeConfig:
    """Serializable OCR knobs passed to the long-lived worker."""

    ocr_enabled: bool = True
    ocr_device: str = "cpu"
    ocr_engine: str = "paddle_static"
    ocr_detection_model_name: str = "PP-OCRv5_mobile_det"
    ocr_recognition_model_name: str = "PP-OCRv5_mobile_rec"
    ocr_model_root: str = "./.models/paddleocr"
    ocr_cpu_threads: int = 4
    ocr_recognition_batch_size: int = 1
    ocr_render_dpi: int = 200
    ocr_visibility_probe_dpi: int = 96
    ocr_min_effective_dpi: int = 120
    ocr_max_render_pixels: int = 40_000_000
    ocr_max_render_side_pixels: int = 6000
    # Bounded default from Phase 4.3 detector-side matrix (see docs/phases).
    ocr_text_det_limit_side_len: int = 1600
    ocr_text_det_limit_type: str = "max"
    ocr_text_det_thresh: float = 0.30
    ocr_text_det_box_thresh: float = 0.60
    ocr_text_det_unclip_ratio: float = 1.50
    ocr_min_recognition_score: float = 0.30
    ocr_low_confidence_score: float = 0.75
    ocr_enable_grayscale_fallback: bool = True
    ocr_fallback_max_attempts: int = 1
    ocr_page_timeout_seconds: float = 180.0
    ocr_max_worker_rss_mb: int = 4096
    ocr_worker_recycle_after_pages: int = 500
    ocr_save_rendered_pages: bool = False
    ocr_keep_failed_render: bool = False
    ocr_layout_max_vertical_gap_ratio: float = 0.035
    ocr_layout_min_horizontal_overlap_ratio: float = 0.25
    ocr_column_gap_ratio: float = 0.08
    canonical_page_dimension_tolerance_points: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OcrRuntimeConfig:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass(frozen=True, slots=True)
class VisualPageRef:
    """Canonical page metadata required by the visual worker."""

    page_number: int
    width_points: float
    height_points: float
    intrinsic_rotation: int
    source_type: str


@dataclass(frozen=True, slots=True)
class VisualWorkerRequest:
    """One document OCR job submitted to the long-lived worker."""

    request_id: str
    session_id: str
    document_id: str
    job_id: str
    canonical_pdf_path: str
    pages: list[VisualPageRef]
    page_output_dir: str
    staging_dir: str
    config: OcrRuntimeConfig
    skip_page_numbers: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "document_id": self.document_id,
            "job_id": self.job_id,
            "canonical_pdf_path": self.canonical_pdf_path,
            "pages": [asdict(p) for p in self.pages],
            "page_output_dir": self.page_output_dir,
            "staging_dir": self.staging_dir,
            "config": self.config.to_dict(),
            "skip_page_numbers": list(self.skip_page_numbers),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualWorkerRequest:
        pages = [VisualPageRef(**p) for p in data["pages"]]
        skip = tuple(int(n) for n in data.get("skip_page_numbers", ()))
        return cls(
            request_id=str(data["request_id"]),
            session_id=str(data["session_id"]),
            document_id=str(data["document_id"]),
            job_id=str(data["job_id"]),
            canonical_pdf_path=str(data["canonical_pdf_path"]),
            pages=pages,
            page_output_dir=str(data["page_output_dir"]),
            staging_dir=str(data["staging_dir"]),
            config=OcrRuntimeConfig.from_dict(data["config"]),
            skip_page_numbers=skip,
        )


@dataclass(slots=True)
class RawOcrWord:
    """Adapter-level word before contract validation."""

    text: str
    score: float
    polygon_px: list[tuple[float, float]]
    geometry_source: str
    score_source: str


@dataclass(slots=True)
class RawOcrLine:
    """Adapter-level line before contract validation."""

    text: str
    detection_score: float
    recognition_score: float
    polygon_px: list[tuple[float, float]]
    words: list[RawOcrWord] = field(default_factory=list)


@dataclass(slots=True)
class RenderedPage:
    """One rendered page bitmap plus geometry metadata."""

    page_number: int
    image: Any  # PIL.Image.Image — typed loosely to avoid import at module load
    width_pixels: int
    height_pixels: int
    effective_dpi: float
    render_scale: float
    page_width_points: float
    page_height_points: float
    requested_dpi: float = 200.0
    render_source_policy: str = "pdfium_render"
    downscale_reason: str | None = None
    source_resolution_cap_applied: bool = False
    source_width_px: int | None = None
    source_height_px: int | None = None
    detector_limit_side_len: int | None = None

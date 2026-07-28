"""Typed, validated application settings loaded from the environment.

Every value below defines a Phase 0 configuration contract. Later phases will
consume these to activate processing capabilities; Phase 0 only reads them.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr, TypeAdapter, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Bounded, sensible range for streamed upload chunk size (4 KiB - 16 MiB).
_MIN_UPLOAD_CHUNK_BYTES = 4_096
_MAX_UPLOAD_CHUNK_BYTES = 16_777_216

_HTTP_URL_ADAPTER = TypeAdapter(AnyHttpUrl)
_VALID_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"})


class Settings(BaseSettings):
    """Immutable application settings.

    Values come from environment variables (which override the `.env` file in
    development). Unknown external variables are ignored so the app coexists
    safely with other tooling.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    # Application identity and API surface.
    app_env: str = "development"
    app_name: str = "VeriDemand"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    frontend_origin: str = "http://localhost:5173"

    # Runtime workspace and lifetimes.
    temp_root: Path = Path("./temp")
    session_ttl_seconds: int = Field(default=7200, gt=0)
    export_ttl_seconds: int = Field(default=1800, gt=0)

    # Session lifecycle (Phase 1).
    session_cleanup_interval_seconds: int = Field(default=60, gt=0)
    session_expiring_warning_seconds: int = Field(default=300, ge=0)

    # Session limits.
    max_files_per_session: int = Field(default=25, gt=0)
    max_pages_per_session: int = Field(default=500, gt=0)
    max_single_file_bytes: int = Field(default=104_857_600, gt=0)
    max_session_bytes: int = Field(default=524_288_000, gt=0)

    # Upload streaming and filename limits (Phase 1).
    upload_chunk_bytes: int = Field(
        default=1_048_576, ge=_MIN_UPLOAD_CHUNK_BYTES, le=_MAX_UPLOAD_CHUNK_BYTES
    )
    max_filename_length: int = Field(default=255, gt=0)
    max_image_pixels: int = Field(default=100_000_000, gt=0)

    # DOCX archive-safety limits (Phase 1).
    max_docx_archive_entries: int = Field(default=10_000, gt=0)
    max_docx_uncompressed_bytes: int = Field(default=268_435_456, gt=0)
    max_docx_entry_bytes: int = Field(default=67_108_864, gt=0)
    max_docx_compression_ratio: float = Field(default=100.0, ge=1.0)

    # Server-Sent Events (Phase 1).
    sse_heartbeat_seconds: int = Field(default=15, gt=0)
    sse_replay_max_events: int = Field(default=500, gt=0)
    sse_subscriber_queue_size: int = Field(default=100, gt=0)
    max_sse_connections_per_session: int = Field(default=3, gt=0)

    # Processing queue (Phase 1/2). Single-process runtime: exactly one worker.
    queue_admission_workers: int = Field(default=1, ge=1, le=1)

    # Test-only hold. When > 0, the processor sleeps cooperatively before finishing
    # so E2E can observe queued/canonicalising states. MUST be 0 in production.
    queue_admission_test_delay_seconds: float = Field(default=0.0, ge=0.0, le=60.0)

    # LibreOffice (Phase 2). External runtime requirement, not a Python package.
    libreoffice_executable: str = ""
    libreoffice_timeout_seconds: float = Field(default=120.0, gt=0)
    libreoffice_termination_grace_seconds: float = Field(default=5.0, gt=0)

    # Canonicalisation workers (Phase 2). Hard-capped at one.
    canonicalisation_workers: int = Field(default=1, ge=1, le=1)
    canonicalisation_thread_workers: int = Field(default=1, ge=1, le=1)

    # Deterministic TXT → PDF (Phase 2).
    txt_page_size: str = "LETTER"
    txt_margin_points: float = Field(default=54.0, gt=0)
    txt_font_size_points: float = Field(default=10.0, gt=0)
    txt_leading_points: float = Field(default=12.0, gt=0)
    txt_tab_size: int = Field(default=4, ge=1, le=16)

    # Image → PDF (Phase 2).
    image_canonical_dpi: float = Field(default=96.0, ge=36.0, le=600.0)
    max_canonical_page_points: float = Field(default=14400.0, gt=0)

    # Canonical delivery (Phase 2).
    canonical_file_cache_control: str = "no-store"
    canonical_page_dimension_tolerance_points: float = Field(default=0.5, gt=0)

    # Viewer scale limits (Phase 2; mirrored as frontend constants).
    viewer_min_scale: float = Field(default=0.25, gt=0)
    viewer_max_scale: float = Field(default=4.0, gt=0)
    viewer_scale_step: float = Field(default=0.25, gt=0)

    # Concurrency (document queue remains single-worker).
    heavy_document_workers: int = Field(default=1, gt=0)
    render_concurrency: int = Field(default=1, ge=1, le=1)
    ocr_concurrency: int = Field(default=1, ge=1, le=1)

    # Trust and routing thresholds (Phase 3+).
    native_trust_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    document_visual_authority_failure_ratio: float = Field(default=0.30, ge=0.0, le=1.0)
    printed_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    handwriting_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    uncertain_to_llm: bool = True

    # Native extraction worker (Phase 3).
    native_extraction_timeout_seconds: float = Field(default=600.0, gt=0)
    native_termination_grace_seconds: float = Field(default=5.0, gt=0)
    native_workers: int = Field(default=1, ge=1, le=1)
    native_dedupe_tolerance_points: float = Field(default=1.0, gt=0)
    native_coordinate_tolerance_points: float = Field(default=0.5, gt=0)
    native_min_characters: int = Field(default=8, gt=0)
    native_max_characters_per_page: int = Field(default=250_000, gt=0)
    native_max_words_per_page: int = Field(default=100_000, gt=0)
    native_max_replacement_ratio: float = Field(default=0.005, ge=0.0, le=1.0)
    native_max_control_ratio: float = Field(default=0.002, ge=0.0, le=1.0)
    native_max_private_use_ratio: float = Field(default=0.005, ge=0.0, le=1.0)
    native_max_unassigned_ratio: float = Field(default=0.005, ge=0.0, le=1.0)
    native_max_cid_token_ratio: float = Field(default=0.05, ge=0.0, le=1.0)
    native_max_invalid_geometry_ratio: float = Field(default=0.01, ge=0.0, le=1.0)
    native_max_out_of_bounds_ratio: float = Field(default=0.01, ge=0.0, le=1.0)
    native_max_duplicate_ratio: float = Field(default=0.20, ge=0.0, le=1.0)
    native_max_near_overprint_ratio: float = Field(default=0.08, ge=0.0, le=1.0)
    native_max_duplicate_layer_coverage_ratio: float = Field(default=0.70, ge=0.0, le=1.0)
    native_min_near_duplicate_match_count: int = Field(default=24, ge=1)
    native_min_dominant_offset_support_ratio: float = Field(
        default=0.55, ge=0.0, le=1.0, description="Informational only (Phase 3.5)."
    )
    native_near_overprint_iou_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    native_near_overprint_centre_factor: float = Field(default=0.35, gt=0)
    native_near_overprint_centre_cap_points: float = Field(default=3.5, gt=0)
    native_near_overprint_size_similarity: float = Field(default=0.40, ge=0.0, le=1.0)
    native_offset_cluster_abs_tol: float = Field(default=0.75, gt=0)
    native_offset_cluster_size_factor: float = Field(default=0.08, ge=0.0, le=1.0)
    native_offset_cluster_top_k: int = Field(default=3, ge=1)
    native_path_b_min_coverage: float = Field(default=0.90, ge=0.0, le=1.0)
    native_path_b_min_matches: int = Field(default=48, ge=1)
    native_path_b_min_duplicate_lines: int = Field(default=2, ge=1)
    native_path_b_min_duplicate_regions: int = Field(default=1, ge=1)
    native_region_min_chars: int = Field(default=12, ge=1)
    native_region_severe_ratio: float = Field(default=0.50, ge=0.0, le=1.0)
    native_region_min_matched: int = Field(default=8, ge=1)
    native_max_symbol_only_word_ratio: float = Field(default=0.40, ge=0.0, le=1.0)
    native_max_single_character_word_ratio: float = Field(default=0.75, ge=0.0, le=1.0)
    native_image_dominant_area_ratio: float = Field(default=0.80, ge=0.0, le=1.0)
    native_document_min_failed_pages: int = Field(default=2, gt=0)
    native_trust_policy_version: str = Field(default="phase3-v1.6", min_length=1)

    # Test-only hold during native extraction for cancellation E2E.
    native_extraction_test_delay_seconds: float = Field(default=0.0, ge=0.0, le=60.0)

    # Phase 4 — printed OCR / visual processing.
    ocr_enabled: bool = True
    # Acceptance / test only: fail visual after native, before OCR inference.
    # Never enable in production.
    ocr_inject_visual_failure: bool = False
    ocr_device: str = "cpu"
    ocr_engine: str = "paddle_static"
    ocr_detection_model_name: str = "PP-OCRv5_mobile_det"
    ocr_recognition_model_name: str = "PP-OCRv5_mobile_rec"
    model_root: Path = Path("./.models")
    ocr_model_root: Path = Path("./.models/paddleocr")
    ocr_workers: int = Field(default=1, ge=1, le=2)
    ocr_cpu_threads: int = Field(default=4, ge=1, le=32)
    ocr_recognition_batch_size: int = Field(default=1, ge=1, le=32)
    ocr_render_dpi: int = Field(default=200, gt=0)
    ocr_visibility_probe_dpi: int = Field(default=96, gt=0)
    ocr_min_effective_dpi: int = Field(default=120, gt=0)
    ocr_max_render_pixels: int = Field(default=40_000_000, gt=0)
    ocr_max_render_side_pixels: int = Field(default=6000, gt=0)
    ocr_text_det_limit_side_len: int = Field(default=1600, gt=0)
    ocr_text_det_limit_type: str = "max"
    ocr_text_det_thresh: float = Field(default=0.30, ge=0.0, le=1.0)
    ocr_text_det_box_thresh: float = Field(default=0.60, ge=0.0, le=1.0)
    ocr_text_det_unclip_ratio: float = Field(default=1.50, gt=0)
    ocr_min_recognition_score: float = Field(default=0.30, ge=0.0, le=1.0)
    ocr_low_confidence_score: float = Field(default=0.75, ge=0.0, le=1.0)
    ocr_enable_grayscale_fallback: bool = True
    ocr_fallback_max_attempts: int = Field(default=1, ge=0, le=1)
    ocr_page_timeout_seconds: float = Field(default=180.0, gt=0)
    ocr_document_timeout_seconds: float = Field(default=3600.0, gt=0)
    ocr_worker_startup_timeout_seconds: float = Field(default=180.0, gt=0)
    ocr_termination_grace_seconds: float = Field(default=10.0, gt=0)
    ocr_max_worker_restarts: int = Field(default=2, ge=0, le=10)
    ocr_worker_recycle_after_pages: int = Field(default=500, gt=0)
    ocr_max_worker_rss_mb: int = Field(default=4096, gt=0)
    ocr_save_rendered_pages: bool = False
    ocr_keep_failed_render: bool = False
    ocr_allow_save_rendered_in_production: bool = False
    native_visibility_probe_enabled: bool = True
    native_visibility_min_words: int = Field(default=8, ge=1)
    native_visibility_min_visible_word_ratio: float = Field(default=0.55, ge=0.0, le=1.0)
    native_visibility_min_region_variance: float = Field(default=4.0, ge=0.0)
    native_visibility_min_edge_density: float = Field(default=0.01, ge=0.0, le=1.0)
    ocr_layout_max_vertical_gap_ratio: float = Field(default=0.035, ge=0.0, le=1.0)
    ocr_layout_min_horizontal_overlap_ratio: float = Field(default=0.25, ge=0.0, le=1.0)
    ocr_column_gap_ratio: float = Field(default=0.08, ge=0.0, le=1.0)

    # Phase 4.5 — hybrid page routing, throughput, live progress.
    hybrid_page_routing_enabled: bool = True
    embedded_ocr_visual_agreement_enabled: bool = True
    embedded_ocr_recognition_check_enabled: bool = True
    targeted_region_repair_enabled: bool = True
    ocr_fast_pass_enabled: bool = True
    ocr_primary_limit_side_len: int = Field(default=960, gt=0)
    ocr_fallback_limit_side_len: int = Field(default=1600, gt=0)
    fair_ocr_scheduling_enabled: bool = False
    fair_ocr_page_chunk_size: int = Field(default=5, ge=1, le=32)
    progress_live_clock_interval_ms: int = Field(default=1000, ge=250, le=5000)
    eta_minimum_sample_count: int = Field(default=3, ge=1, le=50)
    eta_stale_after_seconds: float = Field(default=120.0, gt=0)
    page_routing_policy_version: str = Field(default="phase45-v1", min_length=1)
    # Embedded OCR visual-agreement thresholds (centralised policy).
    embedded_ocr_min_native_words: int = Field(default=12, ge=1)
    embedded_ocr_min_native_characters: int = Field(default=40, ge=1)
    embedded_ocr_visual_sample_size: int = Field(default=24, ge=4, le=64)
    embedded_ocr_recognition_sample_size: int = Field(default=8, ge=2, le=32)
    embedded_ocr_min_visible_box_ratio: float = Field(default=0.55, ge=0.0, le=1.0)
    embedded_ocr_min_visual_agreement: float = Field(default=0.70, ge=0.0, le=1.0)
    embedded_ocr_min_recognition_agreement: float = Field(default=0.72, ge=0.0, le=1.0)
    embedded_ocr_targeted_repair_max_fail_ratio: float = Field(default=0.25, ge=0.0, le=1.0)
    embedded_ocr_targeted_repair_max_regions: int = Field(default=6, ge=1, le=32)
    embedded_ocr_targeted_repair_max_coverage: float = Field(default=0.35, ge=0.0, le=1.0)
    embedded_ocr_repair_padding_ratio: float = Field(default=0.04, ge=0.0, le=0.25)
    # Embedded coverage gate (form/grid pages with sparse OCR layers).
    embedded_ocr_min_candidate_box_coverage: float = Field(default=0.12, ge=0.0, le=1.0)
    embedded_ocr_max_ink_outside_candidates_ratio: float = Field(default=0.45, ge=0.0, le=1.0)
    embedded_ocr_max_uncovered_textlike_ratio: float = Field(default=0.40, ge=0.0, le=1.0)
    embedded_ocr_min_form_line_density_for_coverage_gate: float = Field(
        default=0.15, ge=0.0, le=1.0
    )
    embedded_ocr_min_checkbox_density_for_coverage_gate: float = Field(default=0.08, ge=0.0, le=1.0)
    # Blank-page preflight (conservative — prefer false negatives over skipping content).
    blank_page_preflight_enabled: bool = True
    blank_page_max_ink_density: float = Field(default=0.004, ge=0.0, le=1.0)
    blank_page_max_edge_density: float = Field(default=0.008, ge=0.0, le=1.0)
    blank_page_max_variance: float = Field(default=12.0, ge=0.0)
    # Fast-pass adequacy gates.
    ocr_fast_pass_min_detections: int = Field(default=3, ge=0)
    ocr_fast_pass_min_average_confidence: float = Field(default=0.55, ge=0.0, le=1.0)
    ocr_fast_pass_min_coverage: float = Field(default=0.02, ge=0.0, le=1.0)

    # Handwriting classifier (Phase 5 — path reserved only).
    handwriting_classifier_path: Path = Path("./models/handwriting_classifier/model.onnx")

    # Vision provider (future). The key is never exposed in repr/logs/responses.
    openai_api_key: SecretStr = SecretStr("")
    openai_vision_model: str = "gpt-4.1-mini"
    openai_timeout_seconds: int = Field(default=60, gt=0)
    openai_max_retries: int = Field(default=3, ge=0)
    openai_concurrency: int = Field(default=1, gt=0)
    openai_max_regions_per_request: int = Field(default=12, gt=0)
    openai_max_regions_per_document: int = Field(default=500, gt=0)

    # Logging.
    log_level: str = "INFO"
    log_document_text: bool = False

    @field_validator("api_prefix")
    @classmethod
    def _validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("API_PREFIX must start with '/'.")
        return value

    @field_validator("frontend_origin")
    @classmethod
    def _validate_frontend_origin(cls, value: str) -> str:
        _HTTP_URL_ADAPTER.validate_python(value)
        return value

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in _VALID_LOG_LEVELS:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(_VALID_LOG_LEVELS)}.")
        return level

    @model_validator(mode="after")
    def _resolve_ocr_model_root(self) -> Settings:
        # Resolve relative OCR model paths against the repository root so
        # uvicorn --reload, workers, and scripts share one tree offline.
        from backend.app.extraction.visual.model_paths import resolve_ocr_model_root

        resolved = resolve_ocr_model_root(self.ocr_model_root)
        if resolved != self.ocr_model_root:
            object.__setattr__(self, "ocr_model_root", resolved)
        return self

    @model_validator(mode="after")
    def _validate_lifecycle_windows(self) -> Settings:
        if self.session_cleanup_interval_seconds >= self.session_ttl_seconds:
            raise ValueError(
                "SESSION_CLEANUP_INTERVAL_SECONDS must be less than SESSION_TTL_SECONDS."
            )
        if self.session_expiring_warning_seconds >= self.session_ttl_seconds:
            raise ValueError(
                "SESSION_EXPIRING_WARNING_SECONDS must be less than SESSION_TTL_SECONDS."
            )
        if self.libreoffice_termination_grace_seconds >= self.libreoffice_timeout_seconds:
            raise ValueError(
                "LIBREOFFICE_TERMINATION_GRACE_SECONDS must be less than "
                "LIBREOFFICE_TIMEOUT_SECONDS."
            )
        if self.native_termination_grace_seconds >= self.native_extraction_timeout_seconds:
            raise ValueError(
                "NATIVE_TERMINATION_GRACE_SECONDS must be less than "
                "NATIVE_EXTRACTION_TIMEOUT_SECONDS."
            )
        if not self.native_trust_policy_version.strip():
            raise ValueError("NATIVE_TRUST_POLICY_VERSION must be non-empty.")
        page_size = self.txt_page_size.strip().upper()
        if page_size != "LETTER":
            raise ValueError("TXT_PAGE_SIZE must be LETTER in Phase 2.")
        # US Letter: 612 x 792 points; margins must leave a usable content area.
        if self.txt_margin_points * 2 >= 612 or self.txt_margin_points * 2 >= 792:
            raise ValueError("TXT_MARGIN_POINTS must fit inside the LETTER page.")
        if self.txt_leading_points < self.txt_font_size_points:
            raise ValueError("TXT_LEADING_POINTS must be >= TXT_FONT_SIZE_POINTS.")
        if self.viewer_max_scale <= self.viewer_min_scale:
            raise ValueError("VIEWER_MAX_SCALE must be greater than VIEWER_MIN_SCALE.")
        if self.canonical_file_cache_control.strip().lower() != "no-store":
            raise ValueError("CANONICAL_FILE_CACHE_CONTROL must be 'no-store'.")
        if self.ocr_workers < 1 or self.ocr_workers > 2:
            raise ValueError("OCR_WORKERS must be 1 or 2 for the Phase 4.5 target profile.")
        if self.ocr_device.strip().lower() != "cpu":
            raise ValueError("OCR_DEVICE must be 'cpu' for the reproducible Phase 4 baseline.")
        if self.ocr_engine.strip().lower() != "paddle_static":
            raise ValueError("OCR_ENGINE must be 'paddle_static'.")
        if self.ocr_min_effective_dpi > self.ocr_render_dpi:
            raise ValueError("OCR_MIN_EFFECTIVE_DPI must not exceed OCR_RENDER_DPI.")
        if self.ocr_termination_grace_seconds >= self.ocr_page_timeout_seconds:
            raise ValueError(
                "OCR_TERMINATION_GRACE_SECONDS must be less than OCR_PAGE_TIMEOUT_SECONDS."
            )
        if self.ocr_text_det_limit_type.strip().lower() not in {"max", "min"}:
            raise ValueError("OCR_TEXT_DET_LIMIT_TYPE must be 'max' or 'min'.")
        if self.ocr_primary_limit_side_len > self.ocr_fallback_limit_side_len:
            raise ValueError(
                "OCR_PRIMARY_LIMIT_SIDE_LEN must not exceed OCR_FALLBACK_LIMIT_SIDE_LEN."
            )
        if not self.page_routing_policy_version.strip():
            raise ValueError("PAGE_ROUTING_POLICY_VERSION must be non-empty.")
        if (
            self.app_env.strip().lower() == "production"
            and self.ocr_save_rendered_pages
            and not self.ocr_allow_save_rendered_in_production
        ):
            raise ValueError(
                "OCR_SAVE_RENDERED_PAGES cannot be true in production without "
                "OCR_ALLOW_SAVE_RENDERED_IN_PRODUCTION."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return process-wide cached settings.

    Tests should inject a fresh ``Settings`` into ``create_app`` instead of
    mutating this cache, keeping global process state untouched.
    """

    return Settings()

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

    # Processing queue (Phase 1). The runtime-only implementation is single-process
    # and MUST run exactly one admission worker: multiple workers would create
    # independent, inconsistent session registries and queues.
    queue_admission_workers: int = Field(default=1, ge=1, le=1)

    # Concurrency (future processing pipeline).
    heavy_document_workers: int = Field(default=1, gt=0)
    render_concurrency: int = Field(default=2, gt=0)
    ocr_concurrency: int = Field(default=1, gt=0)

    # Rendering (future).
    pdf_render_dpi: int = Field(default=300, gt=0)
    pdf_render_retry_dpi: int = Field(default=400, gt=0)

    # Trust and routing thresholds (future).
    native_trust_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    document_visual_authority_failure_ratio: float = Field(default=0.30, ge=0.0, le=1.0)
    printed_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    handwriting_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    uncertain_to_llm: bool = True

    # OCR / layout (future).
    paddle_device: str = "cpu"
    paddle_ocr_model: str = "PP-OCRv5_mobile"
    paddle_layout_enabled: bool = True

    # Handwriting classifier (future).
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
    def _validate_lifecycle_windows(self) -> Settings:
        if self.session_cleanup_interval_seconds >= self.session_ttl_seconds:
            raise ValueError(
                "SESSION_CLEANUP_INTERVAL_SECONDS must be less than SESSION_TTL_SECONDS."
            )
        if self.session_expiring_warning_seconds >= self.session_ttl_seconds:
            raise ValueError(
                "SESSION_EXPIRING_WARNING_SECONDS must be less than SESSION_TTL_SECONDS."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return process-wide cached settings.

    Tests should inject a fresh ``Settings`` into ``create_app`` instead of
    mutating this cache, keeping global process state untouched.
    """

    return Settings()

"""AppSettings entity + environment loading (docs/contracts/entities/app-settings.md)."""

from __future__ import annotations

import os
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


class AppSettings(BaseModel):
    """Validated runtime configuration. Never return secrets via API."""

    model_config = ConfigDict(extra="forbid")

    session_ttl_minutes: int = Field(default=120, gt=0)
    max_files_per_session: int = Field(default=20, gt=0)
    max_pages_per_session: int = Field(default=300, gt=0)
    max_file_size_mb: int = Field(default=75, gt=0)
    max_total_upload_mb: int = Field(default=250, gt=0)
    ocr_workers: int = Field(default=1)
    ocr_render_dpi: int = Field(default=200, gt=0)
    ocr_retry_dpi: int = Field(default=300, gt=0)
    native_min_chars: int = Field(default=40, gt=0)
    native_min_text_coverage: float = Field(default=0.02, ge=0.0, le=1.0)
    native_max_replacement_ratio: float = Field(default=0.05, ge=0.0, le=1.0)
    native_max_zero_width_or_overlap_ratio: float = Field(default=0.15, ge=0.0, le=1.0)
    native_min_reading_order_score: float = Field(default=0.55, ge=0.0, le=1.0)
    native_likely_scan_image_coverage: float = Field(default=0.60, ge=0.0, le=1.0)
    # B-02 pathological tokenization knobs (0.1-provisional)
    native_long_token_band: int = Field(default=40, gt=0)
    native_max_long_token_ratio: float = Field(default=0.20, ge=0.0, le=1.0)
    native_max_mean_token_length: float = Field(default=24.0, gt=0.0)
    native_max_median_token_length: float = Field(default=18.0, gt=0.0)
    native_min_printable_ratio: float = Field(default=0.90, ge=0.0, le=1.0)
    native_max_control_char_ratio: float = Field(default=0.02, ge=0.0, le=1.0)
    native_max_oversized_box_ratio: float = Field(default=0.20, ge=0.0, le=1.0)
    native_max_cid_ratio: float = Field(default=0.05, ge=0.0, le=1.0)
    ocr_page_mean_conf_low: float = Field(default=0.55, ge=0.0, le=1.0)
    ocr_page_mean_conf_retry_trigger: float = Field(default=0.70, ge=0.0, le=1.0)
    ocr_init_retry_cooldown_ms: int = Field(default=2000, ge=0)
    # B-03 under-detection knobs (0.1-provisional)
    ocr_min_ink_for_coverage_check: float = Field(default=0.08, ge=0.0, le=1.0)
    ocr_min_token_coverage: float = Field(default=0.05, ge=0.0, le=1.0)
    ocr_min_coverage_to_ink_ratio: float = Field(default=0.15, ge=0.0, le=1.0)
    ocr_min_tokens_ink_rich: int = Field(default=25, gt=0)
    ocr_ink_binarize_threshold: int = Field(default=200, ge=0, le=255)
    ocr_under_detection_triggers_retry: bool = True
    ocr_force_for_tests: bool = False
    rule_confidence_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    enable_llm_classification: bool = False
    enable_llm_semantic_extraction: bool = False
    llm_extraction_temperature: float = Field(default=0.0, ge=0.0)
    llm_draft_temperature: float = Field(default=0.2, ge=0.0)
    allow_vision_crop_fallback: bool = True
    allow_final_export_with_red_issues: bool = False
    log_document_text: bool = False

    @field_validator("ocr_workers")
    @classmethod
    def _ocr_workers_must_be_one(cls, value: int) -> int:
        if value != 1:
            raise ValueError("ocr_workers must be == 1 for the prototype")
        return value

    @model_validator(mode="after")
    def _retry_dpi_ge_render(self) -> Self:
        if self.ocr_retry_dpi < self.ocr_render_dpi:
            raise ValueError("ocr_retry_dpi must be >= ocr_render_dpi")
        return self

    @classmethod
    def from_environment(cls, environ: dict[str, str] | None = None) -> Self:
        env = environ if environ is not None else dict(os.environ)
        raw: dict[str, Any] = {}

        int_keys = {
            "SESSION_TTL_MINUTES": "session_ttl_minutes",
            "MAX_FILES_PER_SESSION": "max_files_per_session",
            "MAX_PAGES_PER_SESSION": "max_pages_per_session",
            "MAX_FILE_SIZE_MB": "max_file_size_mb",
            "MAX_TOTAL_UPLOAD_MB": "max_total_upload_mb",
            "OCR_WORKERS": "ocr_workers",
            "OCR_RENDER_DPI": "ocr_render_dpi",
            "OCR_RETRY_DPI": "ocr_retry_dpi",
            "OCR_INIT_RETRY_COOLDOWN_MS": "ocr_init_retry_cooldown_ms",
            "OCR_MIN_TOKENS_INK_RICH": "ocr_min_tokens_ink_rich",
            "OCR_INK_BINARIZE_THRESHOLD": "ocr_ink_binarize_threshold",
            "NATIVE_MIN_CHARS": "native_min_chars",
            "NATIVE_LONG_TOKEN_BAND": "native_long_token_band",
        }
        float_keys = {
            "RULE_CONFIDENCE_THRESHOLD": "rule_confidence_threshold",
            "NATIVE_MIN_TEXT_COVERAGE": "native_min_text_coverage",
            "NATIVE_MAX_REPLACEMENT_RATIO": "native_max_replacement_ratio",
            "NATIVE_MAX_ZERO_WIDTH_OR_OVERLAP_RATIO": "native_max_zero_width_or_overlap_ratio",
            "NATIVE_MIN_READING_ORDER_SCORE": "native_min_reading_order_score",
            "NATIVE_LIKELY_SCAN_IMAGE_COVERAGE": "native_likely_scan_image_coverage",
            "NATIVE_MAX_LONG_TOKEN_RATIO": "native_max_long_token_ratio",
            "NATIVE_MAX_MEAN_TOKEN_LENGTH": "native_max_mean_token_length",
            "NATIVE_MAX_MEDIAN_TOKEN_LENGTH": "native_max_median_token_length",
            "NATIVE_MIN_PRINTABLE_RATIO": "native_min_printable_ratio",
            "NATIVE_MAX_CONTROL_CHAR_RATIO": "native_max_control_char_ratio",
            "NATIVE_MAX_OVERSIZED_BOX_RATIO": "native_max_oversized_box_ratio",
            "NATIVE_MAX_CID_RATIO": "native_max_cid_ratio",
            "OCR_PAGE_MEAN_CONF_LOW": "ocr_page_mean_conf_low",
            "OCR_PAGE_MEAN_CONF_RETRY_TRIGGER": "ocr_page_mean_conf_retry_trigger",
            "OCR_MIN_INK_FOR_COVERAGE_CHECK": "ocr_min_ink_for_coverage_check",
            "OCR_MIN_TOKEN_COVERAGE": "ocr_min_token_coverage",
            "OCR_MIN_COVERAGE_TO_INK_RATIO": "ocr_min_coverage_to_ink_ratio",
            "LLM_EXTRACTION_TEMPERATURE": "llm_extraction_temperature",
            "LLM_DRAFT_TEMPERATURE": "llm_draft_temperature",
        }
        bool_keys = {
            "ENABLE_LLM_CLASSIFICATION": "enable_llm_classification",
            "ENABLE_LLM_SEMANTIC_EXTRACTION": "enable_llm_semantic_extraction",
            "ALLOW_VISION_CROP_FALLBACK": "allow_vision_crop_fallback",
            "ALLOW_FINAL_EXPORT_WITH_RED_ISSUES": "allow_final_export_with_red_issues",
            "LOG_DOCUMENT_TEXT": "log_document_text",
            "OCR_FORCE_FOR_TESTS": "ocr_force_for_tests",
            "OCR_UNDER_DETECTION_TRIGGERS_RETRY": "ocr_under_detection_triggers_retry",
        }

        try:
            for env_name, field in int_keys.items():
                if env_name in env and env[env_name] != "":
                    raw[field] = int(env[env_name])
            for env_name, field in float_keys.items():
                if env_name in env and env[env_name] != "":
                    raw[field] = float(env[env_name])
            for env_name, field in bool_keys.items():
                if env_name in env and env[env_name] != "":
                    raw[field] = parse_bool(env[env_name])
            return cls.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 — surface as ConfigurationError
            raise ConfigurationError(
                "Invalid application configuration. Check environment variables "
                "(no secrets are included in this message)."
            ) from exc


class ConfigurationError(ValueError):
    """Raised when AppSettings cannot be loaded from the environment."""


def get_safe_config_summary(settings: AppSettings) -> dict[str, int | bool | float]:
    """Non-sensitive subset for health capabilities."""
    return {
        # ocr_enabled is filled by HealthService (avoids models→services import)
        "ocr_enabled": False,
        "llm_classification_enabled": settings.enable_llm_classification,
        "llm_semantic_extraction_enabled": settings.enable_llm_semantic_extraction,
        "rule_confidence_threshold": settings.rule_confidence_threshold,
        "max_files_per_session": settings.max_files_per_session,
        "max_pages_per_session": settings.max_pages_per_session,
    }

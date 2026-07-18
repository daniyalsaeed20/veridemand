"""Unit tests for AppSettings and helpers."""

from __future__ import annotations

import pytest

from app.models.app_settings import (
    AppSettings,
    ConfigurationError,
    get_safe_config_summary,
    parse_bool,
)
from app.models.geometry import normalize_polygon, validate_normalized_polygon


def test_defaults() -> None:
    settings = AppSettings()
    assert settings.session_ttl_minutes == 120
    assert settings.ocr_workers == 1
    assert settings.enable_llm_semantic_extraction is False
    assert settings.log_document_text is False


def test_ocr_workers_must_be_one() -> None:
    with pytest.raises(ValueError):
        AppSettings(ocr_workers=2)


def test_from_environment_invalid_bool() -> None:
    with pytest.raises(ConfigurationError):
        AppSettings.from_environment({"ENABLE_LLM_SEMANTIC_EXTRACTION": "maybe"})


def test_from_environment_override() -> None:
    settings = AppSettings.from_environment(
        {
            "MAX_FILES_PER_SESSION": "10",
            "ENABLE_LLM_SEMANTIC_EXTRACTION": "true",
        }
    )
    assert settings.max_files_per_session == 10
    assert settings.enable_llm_semantic_extraction is True


def test_safe_config_summary_no_secrets() -> None:
    summary = get_safe_config_summary(AppSettings())
    assert "ocr_enabled" in summary
    assert summary["ocr_enabled"] is False
    blob = str(summary)
    assert "password" not in blob
    assert "path" not in blob


def test_parse_bool() -> None:
    assert parse_bool("true") is True
    assert parse_bool("0") is False
    with pytest.raises(ValueError):
        parse_bool("nope")


def test_normalized_polygon_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        validate_normalized_polygon([(0.0, 0.0), (1.5, 0.0), (0.0, 1.0)])


def test_normalize_polygon() -> None:
    result = normalize_polygon(
        [(0.0, 0.0), (100.0, 0.0), (100.0, 200.0), (0.0, 200.0)], 100.0, 200.0
    )
    assert result[1] == (1.0, 0.0)

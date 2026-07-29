from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.settings.config import Settings


def test_defaults_load() -> None:
    settings = Settings()
    assert settings.app_name == "VeriDemand"
    assert settings.app_version == "0.1.0"
    assert settings.api_prefix == "/api/v1"
    assert settings.native_trust_threshold == 0.75
    assert settings.temp_root == Path("temp")


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "CustomName")
    monkeypatch.setenv("MAX_FILES_PER_SESSION", "7")
    settings = Settings()
    assert settings.app_name == "CustomName"
    assert settings.max_files_per_session == 7


def test_invalid_threshold_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(native_trust_threshold=1.5)


def test_invalid_origin_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(frontend_origin="not-a-valid-url")


def test_invalid_api_prefix_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(api_prefix="api/v1")


def test_non_positive_limits_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(max_files_per_session=0)


def test_secret_is_not_exposed_in_repr() -> None:
    settings = Settings(openai_api_key="super-secret-value")
    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings)
    assert settings.openai_api_key.get_secret_value() == "super-secret-value"


def test_fair_scheduler_quantum_defaults() -> None:
    settings = Settings()
    assert settings.fair_ocr_scheduling_enabled is True
    assert settings.fair_ocr_page_quantum == 2
    assert settings.fair_repair_page_quantum == 2
    assert settings.short_document_heavy_page_threshold == 3
    assert settings.scheduler_policy_version == "correction7-v1"


def test_fair_ocr_page_quantum_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAIR_OCR_PAGE_QUANTUM", "7")
    settings = Settings()
    assert settings.fair_ocr_page_quantum == 7


def test_fair_ocr_page_chunk_size_migrates_to_quantum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FAIR_OCR_PAGE_QUANTUM", raising=False)
    monkeypatch.setenv("FAIR_OCR_PAGE_CHUNK_SIZE", "5")
    settings = Settings()
    assert settings.fair_ocr_page_quantum == 5


def test_fair_ocr_page_quantum_wins_over_deprecated_chunk_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAIR_OCR_PAGE_CHUNK_SIZE", "5")
    monkeypatch.setenv("FAIR_OCR_PAGE_QUANTUM", "3")
    settings = Settings()
    assert settings.fair_ocr_page_quantum == 3


def test_invalid_fair_ocr_page_quantum_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(fair_ocr_page_quantum=0)

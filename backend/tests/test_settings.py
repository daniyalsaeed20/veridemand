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

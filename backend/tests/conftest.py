from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.settings.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointed at an isolated, writable temporary workspace."""

    return Settings(temp_root=tmp_path / "temp")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client

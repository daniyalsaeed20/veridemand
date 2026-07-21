from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.contracts.health import LivenessResponse, ReadinessResponse
from backend.app.main import create_app
from backend.app.settings.config import Settings

_HEX_ID = re.compile(r"^[0-9a-f]{32}$")


def test_liveness_returns_200_and_matches_contract(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200

    body = response.json()
    model = LivenessResponse.model_validate(body)
    assert model.status == "ok"
    assert model.service == "veridemand-api"
    assert model.timestamp.tzinfo is not None
    assert model.timestamp.utcoffset() is not None
    assert model.request_id

    # Header and body request ids match.
    assert response.headers["X-Request-ID"] == model.request_id


def test_liveness_timestamp_is_utc(client: TestClient) -> None:
    body = client.get("/health/live").json()
    parsed = datetime.fromisoformat(body["timestamp"])
    offset = parsed.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0


def test_readiness_ready_when_temp_writable(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200

    model = ReadinessResponse.model_validate(response.json())
    assert model.status == "ready"

    check_names = {check.name: check for check in model.checks}
    assert check_names["settings"].status == "pass"
    assert check_names["temp_storage"].status == "pass"


def test_readiness_reports_future_dependencies_as_not_configured(client: TestClient) -> None:
    model = ReadinessResponse.model_validate(client.get("/health/ready").json())
    future = {c.name: c for c in model.checks if not c.required}
    for name in ("libreoffice", "paddle_ocr", "handwriting_classifier", "openai_vision"):
        assert future[name].status == "not_configured"


def test_readiness_503_when_temp_not_writable(tmp_path: Path) -> None:
    # Point TEMP_ROOT beneath a regular file so directory creation fails.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    unusable = Settings(temp_root=blocker / "temp")

    with TestClient(create_app(unusable)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    temp_check = next(c for c in body["checks"] if c["name"] == "temp_storage")
    assert temp_check["status"] == "fail"


def test_incoming_request_id_is_preserved(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "valid-request-123"})
    assert response.headers["X-Request-ID"] == "valid-request-123"
    assert response.json()["request_id"] == "valid-request-123"


def test_missing_request_id_is_generated(client: TestClient) -> None:
    response = client.get("/health/live")
    assert _HEX_ID.match(response.headers["X-Request-ID"])


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "bad id with spaces!"})
    generated = response.headers["X-Request-ID"]
    assert generated != "bad id with spaces!"
    assert _HEX_ID.match(generated)


def test_oversized_request_id_is_replaced(client: TestClient) -> None:
    oversized = "a" * 500
    response = client.get("/health/live", headers={"X-Request-ID": oversized})
    assert response.headers["X-Request-ID"] != oversized
    assert _HEX_ID.match(response.headers["X-Request-ID"])

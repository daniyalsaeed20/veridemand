"""Integration tests for FastAPI health and errors."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.server_settings import ServerSettings
from app.main import create_app
from app.models.app_settings import AppSettings
from app.models.health import HealthResponse


def _client() -> TestClient:
    app = create_app(
        app_settings=AppSettings(),
        server_settings=ServerSettings(
            cors_origins=["http://localhost:5173"],
            log_level="INFO",
            app_version="0.0.0-dev",
        ),
    )
    return TestClient(app)


def test_health_endpoint_schema() -> None:
    with _client() as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"].startswith("req_")
        body = HealthResponse.model_validate(response.json())
        assert body.status == "ok"
        assert body.api_version == "v1"
        assert body.contracts_version == "0.1"
        assert body.app_version == "0.0.0-dev"
        caps = body.capabilities
        if isinstance(caps, dict):
            assert caps["ocr_enabled"] is False
        else:
            assert caps.ocr_enabled is False


def test_unknown_route_error_envelope() -> None:
    with _client() as client:
        response = client.get("/api/v1/does-not-exist")
        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == "route_not_found"
        assert "message" in data
        assert data["request_id"].startswith("req_")
        assert "X-Request-ID" in response.headers


def test_request_id_propagated() -> None:
    with _client() as client:
        response = client.get("/api/v1/health", headers={"X-Request-ID": "req_custom123"})
        assert response.headers["X-Request-ID"] == "req_custom123"

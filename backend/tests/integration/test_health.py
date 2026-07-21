"""Integration tests for FastAPI health and error envelope."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.server_settings import ServerSettings
from app.main import create_app
from app.models.health import HealthResponse


def _client() -> TestClient:
    app = create_app(
        server_settings=ServerSettings(
            cors_origins=["http://localhost:5173"],
            log_level="INFO",
            app_version="0.0.0-dev",
        )
    )
    return TestClient(app)


def test_liveness_endpoint_schema() -> None:
    with _client() as client:
        response = client.get("/api/v1/health/live")
        assert response.status_code == 200
        assert response.headers["X-Request-ID"].startswith("req_")
        body = HealthResponse.model_validate(response.json())
        assert body.status == "ok"
        assert body.api_version == "v1"
        assert body.contracts_version == "0.1"
        assert body.app_version == "0.0.0-dev"


def test_readiness_endpoint_schema() -> None:
    with _client() as client:
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 200
        body = HealthResponse.model_validate(response.json())
        assert body.status == "ok"


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
        response = client.get("/api/v1/health/live", headers={"X-Request-ID": "req_custom123"})
        assert response.headers["X-Request-ID"] == "req_custom123"

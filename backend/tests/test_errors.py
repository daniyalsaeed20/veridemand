from __future__ import annotations

from fastapi import Query
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.settings.config import Settings


def test_unknown_route_returns_canonical_404(client: TestClient) -> None:
    response = client.get("/definitely-not-a-route")
    assert response.status_code == 404

    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert error["code"] == "not_found"
    assert error["message"]
    assert error["request_id"]
    assert error["document_id"] is None
    assert error["page_number"] is None
    assert error["details"] == {}


def test_method_not_allowed_returns_canonical_envelope(client: TestClient) -> None:
    response = client.post("/health/live")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_validation_error_returns_canonical_envelope(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/api/v1/_probe")
    async def _probe(count: int = Query()) -> dict[str, int]:  # pragma: no cover - test probe
        return {"count": count}

    with TestClient(app) as client:
        response = client.get("/api/v1/_probe")

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "errors" in body["error"]["details"]


def test_errors_do_not_leak_stack_traces_or_paths(client: TestClient) -> None:
    for response in (client.get("/nope"), client.post("/health/ready")):
        text = response.text
        assert "Traceback" not in text
        assert "backend/app" not in text
        assert "backend\\app" not in text

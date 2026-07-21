from __future__ import annotations

from pathlib import Path

from scripts.generate_contracts import OUTPUT_PATH, build_openapi, render

from backend.app.main import create_app


def test_health_paths_exist() -> None:
    schema = create_app().openapi()
    assert "/health/live" in schema["paths"]
    assert "/health/ready" in schema["paths"]


def test_operation_ids_are_stable_and_unique() -> None:
    schema = create_app().openapi()
    operation_ids = [
        operation["operationId"]
        for path in schema["paths"].values()
        for operation in path.values()
        if "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))
    assert {"health_live", "health_ready"}.issubset(set(operation_ids))


def test_expected_schemas_exist() -> None:
    schema = create_app().openapi()
    components = schema["components"]["schemas"]
    for name in (
        "LivenessResponse",
        "ReadinessResponse",
        "DependencyCheck",
        "ApiErrorEnvelope",
        "ApiErrorDetail",
    ):
        assert name in components


def test_committed_openapi_matches_generated() -> None:
    committed = Path(OUTPUT_PATH).read_bytes()
    expected = render(build_openapi())
    assert committed == expected, "docs/contracts/openapi.json is out of date"

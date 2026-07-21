"""Contract / schema unit tests for the foundation shell."""

from __future__ import annotations

import json
from pathlib import Path

from app.models.health import HealthResponse
from app.models.registry import ContractRegistry

ROOT = Path(__file__).resolve().parents[3]


def test_schema_generation_contains_only_shell_contracts() -> None:
    schemas = ContractRegistry().json_schemas()
    assert set(schemas) == {"HealthResponse", "ErrorEnvelope"}
    assert schemas["HealthResponse"]["title"] == "HealthResponse"


def test_health_fixture_validates() -> None:
    fixture = json.loads((ROOT / "fixtures" / "health-ok.json").read_text(encoding="utf-8"))
    model = HealthResponse.model_validate(fixture)
    assert model.contracts_version == "0.1"
    assert model.status == "ok"

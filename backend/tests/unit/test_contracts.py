"""Contract / schema unit tests."""

from __future__ import annotations

import json
from pathlib import Path

from app.models.health import HealthResponse
from app.models.money import parse_money_string
from app.models.registry import ContractRegistry
from app.models.source_token import SourceToken

ROOT = Path(__file__).resolve().parents[3]


def test_schema_generation() -> None:
    schemas = ContractRegistry().json_schemas()
    assert "HealthResponse" in schemas
    assert "Fact" in schemas
    assert "BillingEntry" in schemas
    assert schemas["HealthResponse"]["title"] == "HealthResponse"


def test_health_fixture_validates() -> None:
    fixture = json.loads((ROOT / "fixtures" / "health-ok.json").read_text(encoding="utf-8"))
    model = HealthResponse.model_validate(fixture)
    assert model.contracts_version == "0.1"
    assert model.capabilities.ocr_enabled is False  # type: ignore[union-attr]


def test_money_string_rejects_floatish_scientific() -> None:
    assert parse_money_string("150.00") == "150.00"
    try:
        parse_money_string("1e2")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_source_token_rejects_unnormalized_polygon() -> None:
    try:
        SourceToken.model_validate(
            {
                "id": "tok_01",
                "document_id": "doc_01",
                "page_number": 1,
                "text": "x",
                "confidence": 1.0,
                "polygon": [[0, 0], [1200, 0], [1200, 40], [0, 40]],
                "method": "ocr",
            }
        )
        ok = True
    except Exception:
        ok = False
    assert ok is False

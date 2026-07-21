"""ContractRegistry — export JSON Schema for contracted entities."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.models.error_envelope import ErrorEnvelope
from app.models.health import HealthResponse

ENTITY_MODELS: dict[str, type[BaseModel]] = {
    "HealthResponse": HealthResponse,
    "ErrorEnvelope": ErrorEnvelope,
}


class ContractRegistry:
    """Export JSON Schema artifacts for FE generation and contract tests."""

    def json_schemas(self) -> dict[str, dict[str, Any]]:
        return {
            name: model.model_json_schema(mode="serialization")
            for name, model in ENTITY_MODELS.items()
        }

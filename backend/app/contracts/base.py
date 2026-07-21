"""Shared strict base model for all public API contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Strict base model for every public request/response contract.

    Rejects unknown fields, validates on assignment, and allows population by
    either field name or alias so generated clients stay predictable.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )

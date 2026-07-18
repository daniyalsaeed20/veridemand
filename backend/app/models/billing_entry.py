"""BillingEntry entity — money as decimal strings."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.money import MoneyString


class BillingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    document_id: str | None = None
    provider: str | None = None
    service_date: str | None = None
    code: str | None = None
    description: str | None = None
    charge: MoneyString | None = None
    payment: MoneyString | None = None
    adjustment: MoneyString | None = None
    balance: MoneyString | None = None
    currency: str = "USD"
    source_span_ids: list[str] = Field(default_factory=list)
    reconciliation_ok: bool | None = None
    reconciliation_note: str | None = None
    fact_ids: list[str] | None = None

    @field_validator("id")
    @classmethod
    def _bil_prefix(cls, value: str) -> str:
        if not value.startswith("bil_"):
            raise ValueError("id must start with bil_")
        return value

    @field_validator("session_id")
    @classmethod
    def _ses_prefix(cls, value: str) -> str:
        if not value.startswith("ses_"):
            raise ValueError("session_id must start with ses_")
        return value

    @field_validator("document_id")
    @classmethod
    def _doc_prefix(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("doc_"):
            raise ValueError("document_id must start with doc_")
        return value

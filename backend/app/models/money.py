"""Money helpers: JSON decimal strings; Decimal for computation."""

from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import AfterValidator


def parse_money_string(value: str) -> str:
    """Validate a decimal money string without converting to float."""
    try:
        normalized = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("money must be a decimal string") from exc
    if not value or any(ch in value.lower() for ch in ("e", "n", "i")):
        # Reject scientific / NaN / Inf textual forms
        if "e" in value.lower() or value.lower() in {"nan", "inf", "-inf", "+inf"}:
            raise ValueError("money must be a plain decimal string")
    # Preserve canonical string form without binary float
    _ = normalized
    return value


MoneyString = Annotated[str, AfterValidator(parse_money_string)]


def to_decimal(value: str) -> Decimal:
    return Decimal(value)

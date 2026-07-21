"""Generic API error codes and contracts version for the foundation shell."""

from enum import StrEnum
from typing import Final


class ErrorCode(StrEnum):
    ROUTE_NOT_FOUND = "route_not_found"
    VALIDATION_ERROR = "validation_error"
    INTERNAL_ERROR = "internal_error"
    NOT_IMPLEMENTED = "not_implemented"


CONTRACTS_VERSION: Final[str] = "0.1"

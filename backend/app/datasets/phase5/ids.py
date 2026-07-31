"""Opaque identifier generators for Phase 5 dataset records."""

from __future__ import annotations

import secrets
import string
from typing import Final

_ALPHABET: Final = string.ascii_lowercase + string.digits


def _token(n: int = 16) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def new_source_group_id() -> str:
    return f"srcgrp_{_token()}"


def new_document_id() -> str:
    return f"doc_{_token()}"


def new_page_id() -> str:
    return f"page_{_token()}"


def new_crop_id() -> str:
    return f"crop_{_token()}"


def new_review_id() -> str:
    return f"review_{_token()}"


def new_exclusion_id() -> str:
    return f"excl_{_token()}"


def new_duplicate_family_id() -> str:
    return f"dupfam_{_token()}"


def new_pilot_crop_id() -> str:
    return f"pilot_{_token()}"


def new_coverage_event_id() -> str:
    return f"cov_{_token()}"

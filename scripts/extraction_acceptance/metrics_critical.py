"""Critical-field exact-match scoring (extraction fidelity only)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class CriticalFieldResult:
    field_id: str
    field_type: str
    match: bool
    review_required: bool
    layer_used: str | None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CriticalFieldMetrics:
    exact_match_rate: float
    matched: int
    total: int
    uncertain_accepted_count: int
    results: list[CriticalFieldResult]

    def as_dict(self) -> dict:
        d = asdict(self)
        return d


def normalize_critical(value: str, field_type: str) -> str:
    v = " ".join((value or "").split())
    ft = (field_type or "").lower()
    if ft in {"person_name", "law_firm_name"}:
        return v.casefold()
    if ft == "date":
        # keep digits and separators for loose compare after stripping
        return re.sub(r"[^\d/\-]", "", v)
    if ft in {"money", "monetary"}:
        try:
            cleaned = v.replace("$", "").replace(",", "").strip()
            return str(Decimal(cleaned))
        except (InvalidOperation, ValueError):
            return v.casefold()
    if ft in {"badge_id", "id", "claim_number", "policy_number", "report_number"}:
        return re.sub(r"\s+", "", v).casefold()
    if ft in {"medical_code", "cpt", "icd"}:
        return re.sub(r"\s+", "", v).upper()
    return v.casefold()


def score_critical_fields(fields: list[dict]) -> CriticalFieldMetrics:
    """Each field: field_id, field_type, expected, hypothesized,
    uncertain (bool), accepted (bool), review_required (bool), layer_used.
    """
    if not fields:
        return CriticalFieldMetrics(1.0, 0, 0, 0, [])
    results: list[CriticalFieldResult] = []
    matched = 0
    uncertain_accepted = 0
    for f in fields:
        expected = normalize_critical(str(f.get("expected") or ""), str(f.get("field_type") or ""))
        hyp = normalize_critical(str(f.get("hypothesized") or ""), str(f.get("field_type") or ""))
        is_match = expected == hyp and expected != ""
        if is_match:
            matched += 1
        if f.get("uncertain") and f.get("accepted"):
            uncertain_accepted += 1
        results.append(
            CriticalFieldResult(
                field_id=str(f.get("field_id") or ""),
                field_type=str(f.get("field_type") or ""),
                match=is_match,
                review_required=bool(f.get("review_required")),
                layer_used=f.get("layer_used"),
            )
        )
    return CriticalFieldMetrics(
        exact_match_rate=matched / len(fields),
        matched=matched,
        total=len(fields),
        uncertain_accepted_count=uncertain_accepted,
        results=results,
    )

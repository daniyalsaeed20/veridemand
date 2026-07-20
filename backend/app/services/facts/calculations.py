"""Phase 5 deterministic calculations (not full Phase 6 ledger/timeline)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from app.models.enums import FactStatus
from app.models.fact import Fact
from app.services.session.workspace import new_opaque_id


def _parse_iso(value: str) -> date | None:
    try:
        parts = value.split("-")
        if len(parts) != 3:
            return None
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def calculate_service_ranges(session_id: str, facts: list[Fact]) -> list[Fact]:
    visits = [
        f
        for f in facts
        if f.fact_type == "medical.visit_date"
        and f.normalized_value
        and f.status not in {FactStatus.REJECTED}
    ]
    dates: list[date] = []
    input_ids: list[str] = []
    for f in visits:
        d = _parse_iso(str(f.normalized_value))
        if d is not None:
            dates.append(d)
            input_ids.append(f.id)
    if not dates:
        return []
    lo, hi = min(dates), max(dates)
    display = f"{lo.isoformat()} … {hi.isoformat()}"
    return [
        Fact(
            id=new_opaque_id("fact"),
            session_id=session_id,
            fact_type="calc.service_date_range",
            raw_value=display,
            normalized_value=f"{lo.isoformat()}/{hi.isoformat()}",
            display_value=display,
            description=f"calc:service_range|inputs:{','.join(input_ids)}",
            confidence=1.0,
            status=FactStatus.SUGGESTED,
            source_span_ids=[],
            extraction_methods=["calculation"],
            document_ids=None,
            label_context="service_date_range",
            criticality="normal",
            provenance="calculated",
        )
    ]


def count_visits(session_id: str, facts: list[Fact]) -> list[Fact]:
    visits = [
        f
        for f in facts
        if f.fact_type == "medical.visit_date"
        and f.normalized_value
        and f.status not in {FactStatus.REJECTED}
        and f.provenance != "calculated"
    ]
    # Distinct normalized dates
    distinct = sorted({str(f.normalized_value) for f in visits})
    if not distinct:
        return []
    input_ids = [f.id for f in visits]
    return [
        Fact(
            id=new_opaque_id("fact"),
            session_id=session_id,
            fact_type="calc.visit_count",
            raw_value=str(len(distinct)),
            normalized_value=len(distinct),
            display_value=str(len(distinct)),
            description=f"calc:visit_count|inputs:{','.join(input_ids)}",
            confidence=1.0,
            status=FactStatus.SUGGESTED,
            source_span_ids=[],
            extraction_methods=["calculation"],
            label_context="visit_count",
            criticality="normal",
            provenance="calculated",
        )
    ]


def sum_money(
    session_id: str, facts: list[Fact], *, fact_type: str = "damages.charge"
) -> list[Fact]:
    lines = [
        f
        for f in facts
        if f.fact_type == fact_type
        and f.normalized_value is not None
        and f.status not in {FactStatus.REJECTED, FactStatus.CONFLICTING}
        and f.provenance != "calculated"
    ]
    if not lines:
        return []
    total = Decimal("0")
    input_ids: list[str] = []
    for f in lines:
        try:
            total += Decimal(str(f.normalized_value))
            input_ids.append(f.id)
        except InvalidOperation:
            continue
    if not input_ids:
        return []
    norm = format(total, "f")
    return [
        Fact(
            id=new_opaque_id("fact"),
            session_id=session_id,
            fact_type="calc.charges_sum",
            raw_value=norm,
            normalized_value=norm,
            display_value=f"${norm}",
            description=f"calc:sum_money|inputs:{','.join(input_ids)}",
            confidence=1.0,
            status=FactStatus.SUGGESTED,
            source_span_ids=[],
            extraction_methods=["calculation"],
            label_context="charges_sum",
            criticality="normal",
            provenance="calculated",
        )
    ]

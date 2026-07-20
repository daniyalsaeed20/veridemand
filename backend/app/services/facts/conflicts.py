"""Exact-value conflict detection and missing-critical gap Issues."""

from __future__ import annotations

from collections import defaultdict

from app.models.enums import FactStatus, IssueSeverity, IssueStatus
from app.models.fact import Fact
from app.models.issue import Issue
from app.services.facts.types import (
    CONFLICT_ISSUE_BY_FACT_TYPE,
    CRITICAL_FACT_TYPES,
)
from app.services.session.workspace import new_opaque_id


def detect_exact_conflicts(session_id: str, facts: list[Fact]) -> tuple[list[Fact], list[Issue]]:
    """Mark conflicting facts and emit Issues. Does not pick a winner."""
    by_type: dict[str, list[Fact]] = defaultdict(list)
    for fact in facts:
        if fact.status == FactStatus.REJECTED:
            continue
        if fact.normalized_value is None:
            continue
        # Skip calculated aggregates for conflict-of-identity semantics
        if fact.provenance == "calculated":
            continue
        by_type[fact.fact_type].append(fact)

    updated: dict[str, Fact] = {f.id: f for f in facts}
    issues: list[Issue] = []

    for fact_type, members in by_type.items():
        norms = {str(m.normalized_value) for m in members}
        if len(norms) <= 1:
            continue
        # Secondary must not force conflict overwrite of primary-only disagreement visibility
        issue_type = CONFLICT_ISSUE_BY_FACT_TYPE.get(fact_type, "extraction.missing_critical_fact")
        # Use a generic conflict explanation when no dedicated type; prefer claim-style for ids
        if fact_type == "collision.report_number":
            issue_type = "claim.claim_number_conflict"
        fact_ids = [m.id for m in members]
        span_ids: list[str] = []
        doc_ids: list[str] = []
        for m in members:
            span_ids.extend(m.source_span_ids)
            if m.document_ids:
                doc_ids.extend(m.document_ids)
            updated[m.id] = m.model_copy(update={"status": FactStatus.CONFLICTING})

        severity = IssueSeverity.RED if fact_type in CRITICAL_FACT_TYPES else IssueSeverity.AMBER
        issues.append(
            Issue(
                id=new_opaque_id("issue"),
                session_id=session_id,
                issue_type=issue_type
                if issue_type != "extraction.missing_critical_fact"
                else ("identity.name_conflict" if fact_type.endswith(".name") else issue_type),
                severity=severity,
                title=f"Conflicting values for {fact_type}",
                explanation=(
                    f"Multiple normalized values for {fact_type}: "
                    + ", ".join(sorted(norms))
                    + ". All candidates retained; no automatic winner."
                ),
                source_span_ids=list(dict.fromkeys(span_ids)),
                fact_ids=fact_ids,
                document_ids=list(dict.fromkeys(doc_ids)) or None,
                options=["keep_primary", "keep_alternate", "manual_edit"],
                blocking=fact_type in CRITICAL_FACT_TYPES,
                status=IssueStatus.OPEN,
            )
        )

    return list(updated.values()), issues


def create_gap_reviews(
    session_id: str,
    facts: list[Fact],
    *,
    inspected_document_ids: list[str],
) -> list[Issue]:
    """Emit Red Issues for missing critical fields — never invent placeholders."""
    present = {
        f.fact_type
        for f in facts
        if f.status not in {FactStatus.REJECTED}
        and f.normalized_value is not None
        and f.status != FactStatus.CONFLICTING
    }
    # Conflicting still "present" for gap purposes (queued via conflict)
    present |= {f.fact_type for f in facts if f.status == FactStatus.CONFLICTING}

    issues: list[Issue] = []
    for fact_type in sorted(CRITICAL_FACT_TYPES):
        if fact_type in present:
            continue
        # demand.* are user-supplied — separate catalog; skip auto gap here except specials
        if fact_type.startswith("demand."):
            continue
        issues.append(
            Issue(
                id=new_opaque_id("issue"),
                session_id=session_id,
                issue_type="extraction.missing_critical_fact",
                severity=IssueSeverity.RED,
                title=f"Missing critical fact: {fact_type}",
                explanation=(
                    f"No valid deterministic extraction for {fact_type}. "
                    "Do not invent a value; complete via review."
                ),
                source_span_ids=[],
                fact_ids=None,
                document_ids=list(inspected_document_ids) or None,
                options=["manual_enter", "defer"],
                blocking=True,
                status=IssueStatus.OPEN,
            )
        )
    return issues

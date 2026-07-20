"""Authoritative FactService — sole Fact commit boundary for Phase 5 DET."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from app.core.domain_errors import DomainError
from app.core.logging import get_logger
from app.models.app_settings import AppSettings
from app.models.enums import FactStatus
from app.models.fact import Fact, UserOverride
from app.models.issue import Issue
from app.models.taxonomies import ErrorCode
from app.services.facts.calculations import (
    calculate_service_ranges,
    count_visits,
    sum_money,
)
from app.services.facts.conflicts import create_gap_reviews, detect_exact_conflicts
from app.services.facts.consolidate import consolidate_hits
from app.services.facts.eligibility import document_eligibility, filter_usable_spans
from app.services.facts.parsers import parse_document_spans
from app.services.facts.status import score_and_status
from app.services.facts.types import (
    FactExtractionResult,
    FactListResponse,
    FactPatch,
    category_for_fact_type,
)
from app.services.session.service import SessionRecord, SessionService
from app.services.session.workspace import new_opaque_id

logger = get_logger(__name__)

# Issue types owned by fact extraction (replace on re-run)
_FACT_ISSUE_PREFIXES = (
    "extraction.missing_critical_fact",
    "identity.",
    "claim.",
    "collision.date_of_loss_conflict",
    "collision.location_conflict",
    "medical.diagnosis_conflict",
)


class FactService:
    def __init__(
        self,
        *,
        session_service: SessionService,
        app_settings: AppSettings,
    ) -> None:
        self._sessions = session_service
        self._settings = app_settings
        self._llm_calls = 0  # Always zero — no LLM path

    @property
    def llm_call_count(self) -> int:
        return self._llm_calls

    def extract_session_facts(
        self,
        session_id: str,
        generation: int | None = None,
    ) -> FactExtractionResult:
        """Parse eligible evidence into Facts + Issues. Idempotent replace of non-locked."""
        if getattr(self._settings, "enable_llm_semantic_extraction", False):
            # Even if misconfigured, Phase 5 does not call LLM
            logger.warning(
                "LLM semantic extraction flag ignored for Phase 5 DET",
                extra={"extra_fields": {"session_id": session_id}},
            )

        started = time.perf_counter()
        result = FactExtractionResult(llm_calls=0)

        try:
            record = self._sessions.get_record(session_id, touch=False)
        except DomainError:
            return result

        if generation is not None and record.generation != generation:
            return result

        self._run_hook(record, "before_fact_extract")

        locked_facts = [
            f.model_copy(deep=True)
            for f in getattr(record, "facts", [])
            if f.status == FactStatus.LOCKED
        ]

        all_hits = []
        inspected_docs: list[str] = []
        for document in list(record.documents.values()):
            elig = document_eligibility(document)
            if not elig.eligible:
                result.documents_suppressed_authority += 1
                continue

            pages = list(record.pages.get(document.id, []))
            spans_by_page = record.spans_by_page.get(document.id, {})
            usable, suppressed_pages, span_count = filter_usable_spans(pages, spans_by_page)
            result.documents_suppressed_quality += suppressed_pages
            result.spans_inspected += span_count
            if not usable:
                continue

            inspected_docs.append(document.id)
            hits = parse_document_spans(
                document,
                pages,
                usable,
                secondary=elig.secondary,
                classification_ambiguous=elig.classification_ambiguous,
            )
            all_hits.extend(hits)
            result.documents_parsed += 1

        # Commit barrier
        try:
            live = self._sessions.get_record(session_id, touch=False)
        except DomainError:
            return result
        if generation is not None and live.generation != generation:
            return result
        if getattr(live, "deleting", False):
            return result

        self._run_hook(live, "before_fact_commit")

        # Re-check after hook (tombstone / generation)
        try:
            live = self._sessions.get_record(session_id, touch=False)
        except DomainError:
            return result
        if generation is not None and live.generation != generation:
            return result

        consolidated = consolidate_hits(all_hits)
        facts: list[Fact] = list(locked_facts)
        for hit in consolidated:
            # Drop hits whose document vanished
            if hit.document_id not in live.documents:
                continue
            conf, status = score_and_status(hit)
            # Secondary never auto-verifies
            if hit.secondary_source and status == FactStatus.VERIFIED:
                status = FactStatus.NEEDS_REVIEW
            desc_parts = [f"parser:{hit.parser_id}"]
            if hit.secondary_source:
                desc_parts.append("authority:secondary")
            if hit.classification_ambiguous:
                desc_parts.append("classification:ambiguous")
            if hit.warnings:
                desc_parts.append("warnings:" + ",".join(hit.warnings))
            facts.append(
                Fact(
                    id=new_opaque_id("fact"),
                    session_id=session_id,
                    fact_type=hit.fact_type,
                    raw_value=hit.raw_value,
                    normalized_value=hit.normalized_value,
                    display_value=hit.display_value,
                    description=";".join(desc_parts),
                    confidence=conf,
                    status=status,
                    source_span_ids=list(hit.source_span_ids),
                    extraction_methods=list(hit.extraction_methods),
                    document_ids=[hit.document_id],
                    label_context=hit.label_context,
                    criticality=hit.criticality,
                    provenance="deterministic",
                )
            )

        # Calculations (code, not parsers)
        calc_facts = (
            calculate_service_ranges(session_id, facts)
            + count_visits(session_id, facts)
            + sum_money(session_id, facts)
        )
        facts.extend(calc_facts)

        facts, conflict_issues = detect_exact_conflicts(session_id, facts)
        gap_issues = create_gap_reviews(session_id, facts, inspected_document_ids=inspected_docs)

        # Atomic replace of non-locked facts + fact-owned issues
        live.facts = facts
        live.fact_generation = getattr(live, "fact_generation", 0) + 1
        live.issues = [
            i
            for i in live.issues
            if not any(
                i.issue_type == p or i.issue_type.startswith(p) for p in _FACT_ISSUE_PREFIXES
            )
        ]
        # Keep classification.ambiguous etc.
        new_issues = conflict_issues + gap_issues
        live.issues.extend(new_issues)

        result.facts = [f.model_copy(deep=True) for f in facts]
        result.issues = [i.model_copy(deep=True) for i in new_issues]
        result.parse_ms = (time.perf_counter() - started) * 1000.0
        result.llm_calls = 0
        return result

    def extract_document_facts(self, session_id: str, document_id: str) -> list[Fact]:
        result = self.extract_session_facts(session_id)
        return [f for f in result.facts if f.document_ids and document_id in f.document_ids]

    def reconcile_facts(self, session_id: str) -> list[Issue]:
        record = self._sessions.get_record(session_id, touch=True)
        facts, conflict_issues = detect_exact_conflicts(session_id, list(record.facts))
        inspected = list(record.documents.keys())
        gap_issues = create_gap_reviews(session_id, facts, inspected_document_ids=inspected)
        record.facts = facts
        record.issues = [
            i
            for i in record.issues
            if not any(
                i.issue_type == p or i.issue_type.startswith(p) for p in _FACT_ISSUE_PREFIXES
            )
        ]
        new_issues = conflict_issues + gap_issues
        record.issues.extend(new_issues)
        return [i.model_copy(deep=True) for i in new_issues]

    def list_facts(self, session_id: str) -> FactListResponse:
        record = self._sessions.get_record(session_id, touch=True)
        facts = [f.model_copy(deep=True) for f in getattr(record, "facts", [])]
        groups: dict[str, list[str]] = {}
        counts: dict[str, int] = {}
        for fact in facts:
            cat = category_for_fact_type(fact.fact_type)
            groups.setdefault(cat, []).append(fact.id)
            key = fact.status.value
            counts[key] = counts.get(key, 0) + 1
        return FactListResponse(facts=facts, groups=groups, counts_by_status=counts)

    def apply_fact_review(self, session_id: str, fact_id: str, patch: FactPatch) -> Fact:
        record = self._sessions.get_record(session_id, touch=True)
        facts = getattr(record, "facts", [])
        target: Fact | None = None
        index = -1
        for i, fact in enumerate(facts):
            if fact.id == fact_id:
                target = fact
                index = i
                break
        if target is None:
            raise DomainError(ErrorCode.FACT_NOT_FOUND, session_id=session_id)

        if target.status == FactStatus.LOCKED and patch.lock is not False:
            raise DomainError(ErrorCode.FACT_LOCKED, session_id=session_id)

        updates: dict[str, object] = {}
        if patch.lock is True:
            updates["status"] = FactStatus.LOCKED
        elif patch.lock is False and target.status == FactStatus.LOCKED:
            updates["status"] = FactStatus.EDITED

        if patch.value is not None:
            if not patch.value.strip():
                raise DomainError(
                    ErrorCode.FACT_INVALID_PATCH,
                    details={"field": "value", "reason": "empty"},
                    session_id=session_id,
                )
            updates["raw_value"] = patch.value
            updates["normalized_value"] = patch.value.strip()
            updates["display_value"] = patch.value.strip()
            updates["status"] = FactStatus.EDITED
            updates["user_override"] = UserOverride(
                value=patch.value,
                reason=patch.reason or "user_edit",
                at=datetime.now(UTC),
            )
            updates["provenance"] = "user"

        if patch.status is not None:
            if patch.status == FactStatus.LOCKED:
                updates["status"] = FactStatus.LOCKED
            else:
                updates["status"] = patch.status

        if not updates:
            raise DomainError(
                ErrorCode.FACT_INVALID_PATCH,
                details={"reason": "empty_patch"},
                session_id=session_id,
            )

        updated = target.model_copy(update=updates)
        facts[index] = updated
        record.facts = facts
        return updated.model_copy(deep=True)

    def _run_hook(self, record: SessionRecord, name: str) -> None:
        hook = self._sessions._test_hooks.get(name)  # noqa: SLF001
        if hook is not None:
            hook()

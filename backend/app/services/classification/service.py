"""ClassificationService — Phase 4 document type and sequence orchestration."""

from __future__ import annotations

from collections.abc import Callable

from app.core.domain_errors import DomainError
from app.core.logging import get_logger
from app.models.app_settings import AppSettings
from app.models.document import Document
from app.models.enums import (
    ClassificationStatus,
    DocumentClassification,
    DocumentStatus,
    IssueSeverity,
    IssueStatus,
    SafetyArchetype,
)
from app.models.issue import Issue
from app.models.taxonomies import ErrorCode
from app.services.classification.archetype import assess_safety_archetype
from app.services.classification.authority import (
    apply_authority_policy,
    enforce_authority_invariant,
    validate_authority_patch,
)
from app.services.classification.decision import select_rule_decision
from app.services.classification.features import build_classification_features
from app.services.classification.rules import score_rules
from app.services.classification.sequence import apply_sequence_order, propose_sequence
from app.services.classification.types import (
    ClassificationDecision,
    DocumentPresentationPatch,
    DocumentSequenceUpdate,
)
from app.services.llm.classifier import classify_with_llm_fallback
from app.services.session.service import SessionRecord, SessionService
from app.services.session.workspace import new_opaque_id

logger = get_logger(__name__)


class ClassificationService:
    def __init__(
        self,
        *,
        session_service: SessionService,
        app_settings: AppSettings,
    ) -> None:
        self._sessions = session_service
        self._settings = app_settings
        self._test_hooks: dict[str, Callable[[], None]] = {}

    def set_test_hook(self, name: str, fn: Callable[[], None] | None) -> None:
        if fn is None:
            self._test_hooks.pop(name, None)
        else:
            self._test_hooks[name] = fn

    def _run_hook(self, name: str) -> None:
        hook = self._test_hooks.get(name)
        if hook is not None:
            hook()

    def classify_session(self, session_id: str, generation: int) -> list[Document]:
        record = self._sessions.get_record(session_id, touch=False)
        if record.generation != generation or record.deleting:
            return []

        results: list[Document] = []
        for doc in list(record.documents.values()):
            if doc.status not in {DocumentStatus.EXTRACTED, DocumentStatus.CLASSIFIED}:
                continue
            if doc.id in record.classification_locked:
                continue
            classified = self._classify_document_locked(record, generation, doc.id)
            if classified is not None:
                results.append(classified)

        if record.generation != generation or record.deleting:
            return results

        proposals = propose_sequence(
            list(record.documents.values()),
            upload_order=record.upload_order,
        )
        apply_sequence_order(proposals, record.documents)
        return results

    def classify_document(
        self,
        session_id: str,
        document_id: str,
        *,
        generation: int | None = None,
    ) -> Document:
        record = self._sessions.get_record(session_id, touch=True)
        gen = generation if generation is not None else record.generation
        if document_id in record.classification_locked:
            raise DomainError(
                ErrorCode.CLASSIFICATION_LOCKED,
                document_id=document_id,
                session_id=session_id,
            )
        result = self._classify_document_locked(record, gen, document_id)
        if result is None:
            raise DomainError(
                ErrorCode.DOCUMENT_INVALID_PATCH,
                message="Document is not eligible for classification.",
                document_id=document_id,
                session_id=session_id,
            )
        return result

    def _classify_document_locked(
        self,
        record: SessionRecord,
        generation: int,
        document_id: str,
    ) -> Document | None:
        if record.generation != generation or record.deleting:
            return None
        doc = record.documents.get(document_id)
        if doc is None:
            return None
        if doc.status not in {DocumentStatus.EXTRACTED, DocumentStatus.CLASSIFIED}:
            return None

        pages = record.pages.get(document_id, [])
        spans = record.spans_by_page.get(document_id, {})
        features = build_classification_features(doc, pages=pages, spans_by_page=spans)

        self._run_hook("before_stage_a")
        archetype = assess_safety_archetype(features)
        self._run_hook("before_stage_b")
        scores = score_rules(features)
        decision = select_rule_decision(
            features,
            scores,
            threshold=self._settings.rule_confidence_threshold,
            archetype=archetype,
        )
        if decision is None:
            return None

        if decision.needs_correction and self._settings.enable_llm_classification:
            llm_decision = classify_with_llm_fallback(
                features,
                candidates=list(decision.candidates),
                enabled=True,
            )
            if llm_decision is not None:
                decision = llm_decision

        self._run_hook("before_classification_commit")

        if record.generation != generation or record.deleting:
            return None
        doc = record.documents.get(document_id)
        if doc is None:
            return None

        self._apply_decision(record, doc, decision)
        self._emit_classified(record, doc)
        return doc.model_copy(deep=True)

    def _apply_decision(
        self,
        record: SessionRecord,
        doc: Document,
        decision: ClassificationDecision,
    ) -> None:
        doc.classification = decision.classification
        doc.classification_confidence = decision.confidence
        doc.classification_reason = decision.reason
        doc.classification_status = decision.classification_status
        doc.safety_archetype = decision.safety_archetype
        doc.classification_conflicts = list(decision.conflicts)
        doc.status = DocumentStatus.CLASSIFIED
        apply_authority_policy(doc, archetype=decision.safety_archetype)
        enforce_authority_invariant(doc)

        if decision.ambiguous or decision.needs_correction:
            self._upsert_ambiguous_issue(record, doc.id, decision.reason)

    def _upsert_ambiguous_issue(
        self,
        record: SessionRecord,
        document_id: str,
        reason: str,
    ) -> None:
        for issue in record.issues:
            if (
                issue.issue_type == "classification.ambiguous"
                and issue.document_ids
                and document_id in issue.document_ids
                and issue.status == IssueStatus.OPEN
            ):
                return
        record.issues.append(
            Issue(
                id=new_opaque_id("issue"),
                session_id=record.session.id,
                issue_type="classification.ambiguous",
                severity=IssueSeverity.AMBER,
                title="Document classification needs review",
                explanation=f"Classification signals conflict or need review. {reason[:200]}",
                document_ids=[document_id],
                blocking=False,
                status=IssueStatus.OPEN,
            )
        )

    def _emit_classified(self, record: SessionRecord, doc: Document) -> None:
        record.event_sequence += 1
        from app.models.process_event import ProcessEvent

        conflicts = (
            ",".join(doc.classification_conflicts[:6]) if doc.classification_conflicts else ""
        )
        safe_msg = (
            f"category={doc.classification.value if doc.classification else 'none'};"
            f"score={doc.classification_confidence};"
            f"status={doc.classification_status.value if doc.classification_status else 'none'};"
            f"safety={doc.safety_archetype.value if doc.safety_archetype else 'none'};"
            f"conflicts={conflicts}"
        )
        record.events.append(
            ProcessEvent(
                sequence=record.event_sequence,
                event="document.classified",
                session_id=record.session.id,
                document_id=doc.id,
                status=doc.classification.value if doc.classification else None,
                message=safe_msg[:500],
                progress=None,
                error_code=None,
            )
        )

    def update_document_presentation(
        self,
        session_id: str,
        document_id: str,
        patch: DocumentPresentationPatch,
    ) -> Document:
        record = self._sessions.get_record(session_id, touch=True)
        doc = record.documents.get(document_id)
        if doc is None:
            raise DomainError(
                ErrorCode.ROUTE_NOT_FOUND,
                document_id=document_id,
                session_id=session_id,
            )

        if patch.revert_to_proposed:
            if document_id in record.classification_locked:
                record.classification_locked.discard(document_id)
            if doc.status in {DocumentStatus.EXTRACTED, DocumentStatus.CLASSIFIED}:
                return self.classify_document(session_id, document_id)

        if patch.display_name is not None:
            doc.display_name = patch.display_name

        prior_safety = doc.safety_archetype
        if patch.classification is not None:
            doc.classification = patch.classification
            doc.classification_reason = f"user-selected: {patch.classification.value}"
            doc.classification_status = ClassificationStatus.PROPOSED
            doc.status = DocumentStatus.CLASSIFIED
            apply_authority_policy(
                doc,
                archetype=doc.safety_archetype or SafetyArchetype.NONE,
                preserve_user_exclude=True,
                preserve_secondary=True,
            )

        validate_authority_patch(
            doc,
            treat_as_secondary_evidence=patch.treat_as_secondary_evidence,
            exclude_from_drafting=patch.exclude_from_drafting,
        )
        if patch.treat_as_secondary_evidence is not None:
            doc.treat_as_secondary_evidence = patch.treat_as_secondary_evidence
        if patch.exclude_from_drafting is not None:
            safety_active = (
                prior_safety is not None and prior_safety != SafetyArchetype.NONE
            ) or doc.classification in {
                DocumentClassification.EXISTING_DEMAND,
                DocumentClassification.TEMPLATE,
            }
            if (
                patch.exclude_from_drafting is False
                and safety_active
                and not patch.confirm_authority_review
                and not patch.confirm_classification
            ):
                if not (
                    patch.treat_as_secondary_evidence is True
                    and doc.classification
                    and doc.classification.value == "existing_demand"
                ):
                    raise DomainError(
                        ErrorCode.DOCUMENT_INVALID_PATCH,
                        details={
                            "field": "exclude_from_drafting",
                            "reason": "safety_confirmation_required",
                        },
                        document_id=document_id,
                        session_id=session_id,
                    )
            doc.exclude_from_drafting = patch.exclude_from_drafting

        if patch.confirm_authority_review:
            if doc.classification is None:
                raise DomainError(
                    ErrorCode.DOCUMENT_INVALID_PATCH,
                    details={"field": "confirm_authority_review"},
                    document_id=document_id,
                    session_id=session_id,
                )
            doc.classification_status = ClassificationStatus.USER_CONFIRMED

        if patch.confirm_classification:
            if doc.classification is None:
                raise DomainError(
                    ErrorCode.DOCUMENT_INVALID_PATCH,
                    details={"field": "confirm_classification"},
                    document_id=document_id,
                    session_id=session_id,
                )
            record.classification_locked.add(document_id)
            doc.classification_status = ClassificationStatus.USER_CONFIRMED
            doc.classification_reason = (
                f"user-confirmed: {doc.classification.value}; " + (doc.classification_reason or "")
            )[:500]
            if doc.safety_archetype and doc.safety_archetype != SafetyArchetype.NONE:
                apply_authority_policy(doc, archetype=doc.safety_archetype)

        enforce_authority_invariant(doc)

        if patch.sequence_index is not None:
            self._apply_single_sequence_move(record, document_id, patch.sequence_index)

        return doc.model_copy(deep=True)

    def _apply_single_sequence_move(
        self,
        record: SessionRecord,
        document_id: str,
        target_index: int,
    ) -> None:
        eligible = [
            d
            for d in record.documents.values()
            if d.status not in {DocumentStatus.REJECTED, DocumentStatus.DUPLICATE}
        ]
        ordered = sorted(
            eligible,
            key=lambda d: (d.sequence_index if d.sequence_index is not None else 9999, d.id),
        )
        ids = [d.id for d in ordered]
        if document_id not in ids:
            raise DomainError(
                ErrorCode.SEQUENCE_INVALID,
                document_id=document_id,
                session_id=record.session.id,
            )
        ids.remove(document_id)
        target_index = max(0, min(target_index, len(ids)))
        ids.insert(target_index, document_id)
        self.update_document_sequence(
            record.session.id,
            DocumentSequenceUpdate(document_ids=ids),
        )

    def update_document_sequence(
        self,
        session_id: str,
        update: DocumentSequenceUpdate,
    ) -> list[Document]:
        record = self._sessions.get_record(session_id, touch=True)
        eligible = {
            d.id
            for d in record.documents.values()
            if d.status not in {DocumentStatus.REJECTED, DocumentStatus.DUPLICATE}
        }
        proposed = update.document_ids

        if len(proposed) != len(set(proposed)):
            raise DomainError(
                ErrorCode.SEQUENCE_INVALID,
                details={"reason": "duplicate_ids"},
                session_id=session_id,
            )
        if set(proposed) != eligible:
            raise DomainError(
                ErrorCode.SEQUENCE_INVALID,
                details={"reason": "incomplete_or_unknown_ids"},
                session_id=session_id,
            )

        for idx, doc_id in enumerate(proposed):
            doc = record.documents[doc_id]
            doc.sequence_index = idx
            enforce_authority_invariant(doc)

        return [record.documents[did].model_copy(deep=True) for did in proposed]

    def is_classification_locked(self, session_id: str, document_id: str) -> bool:
        record = self._sessions.get_record(session_id, touch=False)
        return document_id in record.classification_locked

"""Proposed document sequencing."""

from __future__ import annotations

from app.models.document import Document
from app.models.enums import DocumentClassification, DocumentStatus
from app.services.classification.rules_config import SEQUENCE_RANK
from app.services.classification.types import SequenceProposal


def propose_sequence(
    documents: list[Document],
    *,
    upload_order: dict[str, int],
) -> list[SequenceProposal]:
    eligible = [
        d for d in documents if d.status not in {DocumentStatus.REJECTED, DocumentStatus.DUPLICATE}
    ]

    def sort_key(doc: Document) -> tuple[int, int, str]:
        classification = doc.classification or DocumentClassification.OTHER
        rank = SEQUENCE_RANK.get(classification, 8)
        order = upload_order.get(doc.id, 0)
        return (rank, order, doc.id)

    ordered = sorted(eligible, key=sort_key)
    return [SequenceProposal(document_id=d.id, sequence_index=i) for i, d in enumerate(ordered)]


def apply_sequence_order(
    proposals: list[SequenceProposal],
    documents: dict[str, Document],
) -> None:
    for prop in proposals:
        doc = documents.get(prop.document_id)
        if doc is not None:
            doc.sequence_index = prop.sequence_index

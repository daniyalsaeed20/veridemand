"""Unit tests for proposed document sequencing."""

from __future__ import annotations

from app.models.document import Document
from app.models.enums import DocumentClassification, DocumentFileType, DocumentStatus
from app.services.classification.sequence import propose_sequence


def _doc(doc_id: str, cls: DocumentClassification, order: int) -> Document:
    return Document(
        id=doc_id,
        session_id="ses_test00000000000000001",
        display_name=f"{cls.value}.pdf",
        file_type=DocumentFileType.PDF,
        content_sha256="b" * 64,
        status=DocumentStatus.CLASSIFIED,
        classification=cls,
        sequence_index=None,
    )


def test_propose_sequence_category_order() -> None:
    docs = [
        _doc("doc_bill000000000000000001", DocumentClassification.BILL_LEDGER, 2),
        _doc("doc_pol0000000000000000001", DocumentClassification.POLICE_REPORT, 0),
        _doc("doc_med0000000000000000001", DocumentClassification.MEDICAL_RECORD, 1),
        _doc("doc_dem0000000000000000001", DocumentClassification.EXISTING_DEMAND, 3),
    ]
    upload_order = {d.id: i for i, d in enumerate(docs)}
    proposals = propose_sequence(docs, upload_order=upload_order)
    ids = [p.document_id for p in proposals]
    assert ids.index("doc_pol0000000000000000001") < ids.index("doc_med0000000000000000001")
    assert ids.index("doc_med0000000000000000001") < ids.index("doc_bill000000000000000001")
    assert ids.index("doc_dem0000000000000000001") == len(ids) - 1


def test_sequence_contiguous_indices() -> None:
    docs = [
        _doc("doc_a00000000000000000001", DocumentClassification.OTHER, 0),
        _doc("doc_b00000000000000000002", DocumentClassification.OTHER, 1),
    ]
    proposals = propose_sequence(docs, upload_order={d.id: i for i, d in enumerate(docs)})
    indices = [p.sequence_index for p in proposals]
    assert indices == [0, 1]


def test_sequence_skips_rejected() -> None:
    rejected = Document(
        id="doc_rej000000000000000001",
        session_id="ses_test00000000000000001",
        display_name="bad.pdf",
        file_type=DocumentFileType.PDF,
        content_sha256="c" * 64,
        status=DocumentStatus.REJECTED,
    )
    good = _doc("doc_ok0000000000000000001", DocumentClassification.OTHER, 0)
    proposals = propose_sequence([rejected, good], upload_order={good.id: 0})
    assert len(proposals) == 1
    assert proposals[0].document_id == good.id

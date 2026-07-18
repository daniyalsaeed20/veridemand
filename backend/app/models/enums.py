"""Closed enums from docs/contracts/enums.md (contracts_version 0.1)."""

from enum import StrEnum


class SessionStatus(StrEnum):
    CREATED = "created"
    INGESTING = "ingesting"
    PROCESSING = "processing"
    REVIEWING = "reviewing"
    DRAFTABLE = "draftable"
    DRAFT_REVIEW = "draft_review"
    EXPORTABLE = "exportable"
    EXPIRED = "expired"
    FAILED = "failed"
    DELETED = "deleted"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"
    NORMALIZED = "normalized"
    READY_FOR_EXTRACTION = "ready_for_extraction"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    CLASSIFIED = "classified"
    EXCLUDED = "excluded"


class DocumentFileType(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    JPG = "jpg"
    PNG = "png"
    TIFF = "tiff"


class DocumentClassification(StrEnum):
    POLICE_REPORT = "police_report"
    INSURER_CORRESPONDENCE = "insurer_correspondence"
    MEDICAL_RECORD = "medical_record"
    IMAGING_REPORT = "imaging_report"
    BILL_LEDGER = "bill_ledger"
    LIEN = "lien"
    WAGE_LOSS = "wage_loss"
    PHOTOGRAPHS = "photographs"
    EXISTING_DEMAND = "existing_demand"
    TEMPLATE = "template"
    OTHER = "other"


class ExtractionMethod(StrEnum):
    NATIVE = "native"
    OCR = "ocr"
    MANUAL = "manual"


class PageRoute(StrEnum):
    NATIVE = "native"
    OCR = "ocr"
    MANUAL_REVIEW = "manual_review"


class FactStatus(StrEnum):
    SUGGESTED = "suggested"
    VERIFIED = "verified"
    EDITED = "edited"
    CONFLICTING = "conflicting"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"
    LOCKED = "locked"


class IssueSeverity(StrEnum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class IssueStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    WAIVED = "waived"
    DEFERRED = "deferred"


class ReviewState(StrEnum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class TimelineEventType(StrEnum):
    COLLISION = "collision"
    TREATMENT = "treatment"
    IMAGING = "imaging"
    CORRESPONDENCE = "correspondence"
    BILLING = "billing"
    DISCHARGE = "discharge"
    SETTLEMENT = "settlement"


class DraftSectionType(StrEnum):
    HEADER_RE = "header_re"
    FACTS = "facts"
    LIABILITY = "liability"
    TREATMENT_SUMMARY = "treatment_summary"
    GENERAL_DAMAGES = "general_damages"
    SPECIALS_TABLE = "specials_table"
    SETTLEMENT_PROPOSAL = "settlement_proposal"
    CLOSING = "closing"
    EXHIBIT_LIST = "exhibit_list"
    OTHER = "other"


class StatementSupportLabel(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    LEGAL_CLAUSE = "legal_clause"
    ARGUMENT = "argument"


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    ERROR = "error"


class DecisionAction(StrEnum):
    VERIFY = "verify"
    EDIT = "edit"
    USE_VALUE = "use_value"
    ENTER_VALUE = "enter_value"
    EXCLUDE = "exclude"
    MARK_UNAVAILABLE = "mark_unavailable"
    RESOLVE = "resolve"
    WAIVE = "waive"
    DEFER_ATTORNEY = "defer_attorney"
    LOCK = "lock"


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ExportKind(StrEnum):
    DRAFT = "draft"
    FINAL = "final"

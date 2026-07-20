"""Fact types, issue types, and API error codes from docs/contracts/."""

from enum import StrEnum
from typing import Final

FACT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "client.name",
        "client.dob",
        "client.phone",
        "client.email",
        "client.address",
        "client.pronouns",
        "attorney.name",
        "attorney.phone",
        "attorney.email",
        "insurer.name",
        "insured.name",
        "adjuster.name",
        "claim.number",
        "policy.number",
        "collision.date",
        "collision.time",
        "collision.report_number",
        "collision.location",
        "collision.vehicles",
        "collision.impact_type",
        "collision.airbags",
        "collision.transport",
        "liability.traffic_signal",
        "liability.admission",
        "liability.citation",
        "liability.police_finding",
        "liability.witness",
        "liability.comparative_fault_allegation",
        "medical.provider",
        "medical.provider_phone",
        "medical.visit_date",
        "medical.complaint",
        "medical.pain_score",
        "medical.exam_finding",
        "medical.diagnosis",
        "medical.treatment",
        "medical.medication",
        "imaging.study_date",
        "imaging.modality",
        "imaging.level",
        "imaging.finding",
        "imaging.measurement",
        "imaging.stenosis",
        "imaging.fracture",
        "imaging.recommendation",
        "recovery.improvement",
        "recovery.resolved_symptoms",
        "recovery.discharge",
        "recovery.mmi",
        "recovery.restrictions",
        "recovery.future_care",
        "prior.preexisting_diagnosis",
        "prior.prior_symptoms",
        "prior.asymptomatic_status",
        "prior.aggravation_opinion",
        "damages.charge",
        "damages.payment",
        "damages.adjustment",
        "damages.balance",
        "damages.lien",
        "damages.wage_loss",
        "damages.out_of_pocket",
        "damages.specials_claimed",
        "billing.cpt",
        "calc.visit_count",
        "calc.service_date_range",
        "calc.charges_sum",
        "correspondence.requested_items",
        "correspondence.response_deadline",
        "correspondence.offer_deadline",
        "correspondence.missing_document",
        "demand.authorized_amount",
        "demand.multiplier",
        "demand.offer_expiry",
        "demand.exhibit_order",
    }
)

ISSUE_TYPES: Final[frozenset[str]] = frozenset(
    {
        "extraction.unreadable_page",
        "extraction.low_ocr_confidence",
        "extraction.broken_text_layer",
        "extraction.truncated_text",
        "extraction.suspected_handwriting",
        "extraction.insufficient_ocr_coverage",
        "extraction.missing_critical_fact",
        "classification.ambiguous",
        "identity.name_conflict",
        "identity.dob_conflict",
        "identity.pronoun_conflict",
        "identity.address_conflict",
        "claim.claim_number_conflict",
        "claim.policy_number_conflict",
        "claim.insurer_conflict",
        "collision.date_of_loss_conflict",
        "collision.location_conflict",
        "collision.liability_narrative_conflict",
        "medical.diagnosis_conflict",
        "medical.fracture_conflict",
        "medical.symptom_status_conflict",
        "medical.prior_condition_conflict",
        "medical.future_care_conflict",
        "billing.unreconciled_balance",
        "billing.duplicate_charge",
        "billing.total_mismatch",
        "billing.missing_bill",
        "billing.missing_lien",
        "draft.placeholder",
        "draft.internal_note",
        "draft.unsupported_statement",
        "draft.contradicted_statement",
        "draft.pronoun_mismatch",
        "draft.duplicate_section",
        "exhibits.listed_missing",
        "exhibits.uploaded_unlisted",
        "exhibits.wrong_numbering",
        "user_input.missing_demand_amount",
        "user_input.missing_deadline",
        "user_input.unresolved_attorney_decision",
    }
)


class ErrorCode(StrEnum):
    SESSION_NOT_FOUND = "session_not_found"
    SESSION_EXPIRED = "session_expired"
    SESSION_CLEANUP_FAILED = "session_cleanup_failed"
    SESSION_LIMIT_EXCEEDED = "session_limit_exceeded"
    UPLOAD_UNSUPPORTED_TYPE = "upload_unsupported_type"
    UPLOAD_MIME_MISMATCH = "upload_mime_mismatch"
    UPLOAD_SIGNATURE_MISMATCH = "upload_signature_mismatch"
    UPLOAD_ENCRYPTED_PDF = "upload_encrypted_pdf"
    UPLOAD_CORRUPT_FILE = "upload_corrupt_file"
    UPLOAD_FILE_TOO_LARGE = "upload_file_too_large"
    UPLOAD_PAGE_LIMIT_EXCEEDED = "upload_page_limit_exceeded"
    UPLOAD_TOTAL_SIZE_EXCEEDED = "upload_total_size_exceeded"
    UPLOAD_FILE_COUNT_EXCEEDED = "upload_file_count_exceeded"
    UPLOAD_DUPLICATE = "upload_duplicate"
    UPLOAD_MACROS_NOT_SUPPORTED = "upload_macros_not_supported"
    PROCESS_NOT_READY = "process_not_ready"
    PROCESS_ALREADY_RUNNING = "process_already_running"
    PROCESS_CANCELLED = "process_cancelled"
    PROCESS_STAGE_FAILED = "process_stage_failed"
    EXTRACTION_RENDER_FAILED = "extraction_render_failed"
    EXTRACTION_OCR_FAILED = "extraction_ocr_failed"
    EXTRACTION_NATIVE_FAILED = "extraction_native_failed"
    CLASSIFICATION_LOCKED = "classification_locked"
    DOCUMENT_INVALID_PATCH = "document_invalid_patch"
    SEQUENCE_INVALID = "sequence_invalid"
    FACT_NOT_FOUND = "fact_not_found"
    FACT_LOCKED = "fact_locked"
    FACT_INVALID_PATCH = "fact_invalid_patch"
    ISSUE_NOT_FOUND = "issue_not_found"
    ISSUE_INVALID_RESOLUTION = "issue_invalid_resolution"
    DRAFT_NOT_READY = "draft_not_ready"
    DRAFT_NOT_FOUND = "draft_not_found"
    DRAFT_LLM_SCHEMA_FAILED = "draft_llm_schema_failed"
    EXPORT_BLOCKED_RED_ISSUES = "export_blocked_red_issues"
    EXPORT_BLOCKED_PREFLIGHT = "export_blocked_preflight"
    EXPORT_FAILED = "export_failed"
    ROUTE_NOT_FOUND = "route_not_found"
    VALIDATION_ERROR = "validation_error"
    INTERNAL_ERROR = "internal_error"
    NOT_IMPLEMENTED = "not_implemented"


CONTRACTS_VERSION: Final[str] = "0.1"

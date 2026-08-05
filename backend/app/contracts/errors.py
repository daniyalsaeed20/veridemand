"""Canonical API error contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from backend.app.contracts.base import ApiModel


class ErrorCode(StrEnum):
    """Stable, client-facing error codes used across the API."""

    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    VALIDATION_ERROR = "validation_error"
    CONFIGURATION_ERROR = "configuration_error"
    SERVICE_NOT_READY = "service_not_ready"
    INTERNAL_ERROR = "internal_error"

    # Sessions (Phase 1).
    SESSION_NOT_FOUND = "session_not_found"
    SESSION_EXPIRED = "session_expired"
    SESSION_LIMIT_EXCEEDED = "session_limit_exceeded"
    SESSION_DELETING = "session_deleting"

    # Documents (Phase 1).
    DOCUMENT_NOT_FOUND = "document_not_found"
    DOCUMENT_PROCESSING = "document_processing"
    INVALID_DOCUMENT_STATE = "invalid_document_state"

    # Jobs / queue (Phase 1).
    JOB_NOT_FOUND = "job_not_found"
    JOB_ALREADY_TERMINAL = "job_already_terminal"
    QUEUE_CLOSED = "queue_closed"

    # Uploads (Phase 1).
    UPLOAD_NO_FILES = "upload_no_files"
    UPLOAD_EMPTY_FILE = "upload_empty_file"
    UPLOAD_INVALID_FILENAME = "upload_invalid_filename"
    UPLOAD_UNSUPPORTED_TYPE = "upload_unsupported_type"
    UPLOAD_SIGNATURE_MISMATCH = "upload_signature_mismatch"
    UPLOAD_MIME_MISMATCH = "upload_mime_mismatch"
    UPLOAD_TOO_LARGE = "upload_too_large"
    UPLOAD_ENCRYPTED_PDF = "upload_encrypted_pdf"
    UPLOAD_CORRUPT_FILE = "upload_corrupt_file"
    UPLOAD_MACROS_NOT_SUPPORTED = "upload_macros_not_supported"
    UPLOAD_ARCHIVE_UNSAFE = "upload_archive_unsafe"
    UPLOAD_ARCHIVE_TOO_LARGE = "upload_archive_too_large"
    UPLOAD_IMAGE_TOO_LARGE = "upload_image_too_large"

    # SSE (Phase 1).
    SSE_CONNECTION_LIMIT = "sse_connection_limit"
    SSE_STREAM_CLOSED = "sse_stream_closed"

    # Canonical documents / geometry (Phase 2).
    CANONICAL_DOCUMENT_NOT_READY = "canonical_document_not_ready"
    CANONICAL_DOCUMENT_NOT_FOUND = "canonical_document_not_found"

    CANONICALISATION_FAILED = "canonicalisation_failed"
    CANONICALISATION_CANCELLED = "canonicalisation_cancelled"
    CANONICALISATION_TIMEOUT = "canonicalisation_timeout"
    CANONICALISATION_OUTPUT_MISSING = "canonicalisation_output_missing"
    CANONICALISATION_OUTPUT_INVALID = "canonicalisation_output_invalid"
    CANONICALISATION_PAGE_LIMIT_EXCEEDED = "canonicalisation_page_limit_exceeded"
    CANONICALISATION_EXTERNAL_RESOURCE_NOT_SUPPORTED = (
        "canonicalisation_external_resource_not_supported"
    )
    CANONICALISATION_MULTIFRAME_NOT_SUPPORTED = "canonicalisation_multiframe_not_supported"
    CANONICALISATION_UNSUPPORTED_TEXT_GLYPH = "canonicalisation_unsupported_text_glyph"
    CANONICALISATION_INVALID_PDF = "canonicalisation_invalid_pdf"

    LIBREOFFICE_NOT_FOUND = "libreoffice_not_found"
    LIBREOFFICE_UNAVAILABLE = "libreoffice_unavailable"
    LIBREOFFICE_PROCESS_FAILED = "libreoffice_process_failed"
    LIBREOFFICE_TIMEOUT = "libreoffice_timeout"
    LIBREOFFICE_NOT_AVAILABLE = "libreoffice_not_available"  # alias for readiness

    CANONICAL_PAGE_INVALID = "canonical_page_invalid"
    CANONICAL_PAGE_DIMENSIONS_INVALID = "canonical_page_dimensions_invalid"
    CANONICAL_PAGE_ROTATION_INVALID = "canonical_page_rotation_invalid"

    GEOMETRY_INVALID = "geometry_invalid"
    GEOMETRY_OUT_OF_BOUNDS = "geometry_out_of_bounds"
    GEOMETRY_ZERO_AREA = "geometry_zero_area"
    GEOMETRY_BBOX_MISMATCH = "geometry_bbox_mismatch"

    # Native extraction / trust (Phase 3).
    NATIVE_RESULT_NOT_READY = "native_result_not_ready"
    NATIVE_RESULT_NOT_FOUND = "native_result_not_found"
    NATIVE_PAGE_NOT_FOUND = "native_page_not_found"
    NATIVE_EXTRACTION_FAILED = "native_extraction_failed"
    NATIVE_EXTRACTION_TIMEOUT = "native_extraction_timeout"
    NATIVE_WORKER_NOT_CONFIGURED = "native_worker_not_configured"
    NATIVE_WORKER_START_FAILED = "native_worker_start_failed"
    NATIVE_WORKER_FAILED = "native_worker_failed"
    NATIVE_WORKER_OUTPUT_INVALID = "native_worker_output_invalid"
    NATIVE_RESULT_PUBLISH_FAILED = "native_result_publish_failed"
    NATIVE_CHARACTER_LIMIT_EXCEEDED = "native_character_limit_exceeded"
    NATIVE_WORD_LIMIT_EXCEEDED = "native_word_limit_exceeded"
    NATIVE_PAGE_METADATA_MISMATCH = "native_page_metadata_mismatch"
    NATIVE_PAGE_DIMENSIONS_MISMATCH = "native_page_dimensions_mismatch"
    NATIVE_GEOMETRY_INVALID = "native_geometry_invalid"
    NATIVE_TEXT_REJECTED = "native_text_rejected"
    NATIVE_DOCUMENT_ESCALATED = "native_document_escalated"

    # Visual / printed OCR (Phase 4).
    VISUAL_RESULT_NOT_READY = "visual_result_not_ready"
    VISUAL_RESULT_NOT_FOUND = "visual_result_not_found"
    VISUAL_PAGE_NOT_FOUND = "visual_page_not_found"
    VISUAL_RENDER_FAILED = "visual_render_failed"
    VISUAL_RENDER_DIMENSION_MISMATCH = "visual_render_dimension_mismatch"
    VISUAL_PAGE_RESOURCE_LIMIT = "visual_page_resource_limit"
    OCR_WORKER_NOT_READY = "ocr_worker_not_ready"
    OCR_WORKER_START_FAILED = "ocr_worker_start_failed"
    OCR_WORKER_CRASHED = "ocr_worker_crashed"
    OCR_WORKER_RESTART_LIMIT = "ocr_worker_restart_limit"
    OCR_RETRY_NOT_ALLOWED = "ocr_retry_not_allowed"
    OCR_MODEL_NOT_FOUND = "ocr_model_not_found"
    OCR_MODEL_LOAD_FAILED = "ocr_model_load_failed"
    OCR_RUNTIME_UNAVAILABLE = "ocr_runtime_unavailable"
    OCR_PAGE_TIMEOUT = "ocr_page_timeout"
    OCR_DOCUMENT_TIMEOUT = "ocr_document_timeout"
    OCR_DETECTION_FAILED = "ocr_detection_failed"
    OCR_RECOGNITION_FAILED = "ocr_recognition_failed"
    OCR_RESULT_INVALID = "ocr_result_invalid"
    OCR_NO_TEXT_DETECTED = "ocr_no_text_detected"
    OCR_LOW_CONFIDENCE = "ocr_low_confidence"
    NATIVE_TEXT_NOT_VISUALLY_PRESENT = "native_text_not_visually_present"
    NATIVE_TEXT_VISIBILITY_UNCERTAIN = "native_text_visibility_uncertain"
    NATIVE_TEXT_VISUALLY_SUPPORTED = "native_text_visually_supported"
    VISUAL_GEOMETRY_INVALID = "visual_geometry_invalid"
    VISUAL_RESULT_PUBLISH_FAILED = "visual_result_publish_failed"


class ApiErrorDetail(ApiModel):
    """Structured, non-sensitive description of a single API error."""

    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable, non-sensitive error message.")
    request_id: str = Field(description="Correlates the error with server logs.")
    document_id: str | None = Field(
        default=None, description="Related document identifier when applicable."
    )
    page_number: int | None = Field(
        default=None, gt=0, description="Related 1-based page number when applicable."
    )
    details: dict[str, Any] = Field(
        default_factory=dict, description="Optional structured, non-sensitive context."
    )


class ApiErrorEnvelope(ApiModel):
    """Top-level wrapper returned for every error response."""

    error: ApiErrorDetail = Field(description="The error payload.")

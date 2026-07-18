"""Domain exceptions mapped to contracted error codes and HTTP status."""

from __future__ import annotations

from typing import Any

from app.models.taxonomies import ErrorCode

# Canonical user-facing messages aligned with docs/contracts/error-codes.md
ERROR_MESSAGES: dict[str, str] = {
    ErrorCode.SESSION_NOT_FOUND: "Session not found.",
    ErrorCode.SESSION_EXPIRED: "This temporary session has expired.",
    ErrorCode.SESSION_CLEANUP_FAILED: "The session could not be fully cleaned up.",
    ErrorCode.SESSION_LIMIT_EXCEEDED: "Too many active sessions.",
    ErrorCode.UPLOAD_UNSUPPORTED_TYPE: "This file type is not supported in the prototype.",
    ErrorCode.UPLOAD_MIME_MISMATCH: "File content does not match its declared type.",
    ErrorCode.UPLOAD_SIGNATURE_MISMATCH: "File signature validation failed.",
    ErrorCode.UPLOAD_ENCRYPTED_PDF: "This PDF is password-protected and cannot be processed.",
    ErrorCode.UPLOAD_CORRUPT_FILE: "This file appears corrupt or unreadable.",
    ErrorCode.UPLOAD_FILE_TOO_LARGE: "This file exceeds the maximum size limit.",
    ErrorCode.UPLOAD_PAGE_LIMIT_EXCEEDED: "This file exceeds the page limit for the session.",
    ErrorCode.UPLOAD_TOTAL_SIZE_EXCEEDED: "Total upload size for this session was exceeded.",
    ErrorCode.UPLOAD_FILE_COUNT_EXCEEDED: "Too many files in this session.",
    ErrorCode.UPLOAD_DUPLICATE: "This file is an exact duplicate of another upload.",
}

ERROR_HTTP_STATUS: dict[str, int] = {
    ErrorCode.SESSION_NOT_FOUND: 404,
    ErrorCode.SESSION_EXPIRED: 410,
    ErrorCode.SESSION_CLEANUP_FAILED: 500,
    ErrorCode.SESSION_LIMIT_EXCEEDED: 429,
    ErrorCode.UPLOAD_UNSUPPORTED_TYPE: 400,
    ErrorCode.UPLOAD_MIME_MISMATCH: 400,
    ErrorCode.UPLOAD_SIGNATURE_MISMATCH: 400,
    ErrorCode.UPLOAD_ENCRYPTED_PDF: 400,
    ErrorCode.UPLOAD_CORRUPT_FILE: 400,
    ErrorCode.UPLOAD_FILE_TOO_LARGE: 400,
    ErrorCode.UPLOAD_PAGE_LIMIT_EXCEEDED: 400,
    ErrorCode.UPLOAD_TOTAL_SIZE_EXCEEDED: 400,
    ErrorCode.UPLOAD_FILE_COUNT_EXCEEDED: 400,
}


class DomainError(Exception):
    """Raised for contracted domain failures."""

    def __init__(
        self,
        error_code: str,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        session_id: str | None = None,
        document_id: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.error_code = error_code
        self.message = message or ERROR_MESSAGES.get(error_code, "Request failed.")
        self.details = details or {}
        self.session_id = session_id
        self.document_id = document_id
        self.status_code = status_code or ERROR_HTTP_STATUS.get(error_code, 400)
        super().__init__(self.message)


class UploadFileError(Exception):
    """Per-file upload rejection (does not fail the whole batch HTTP request)."""

    def __init__(
        self,
        error_code: str,
        display_name: str,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.error_code = error_code
        self.display_name = display_name
        self.message = message or ERROR_MESSAGES.get(error_code, "Upload rejected.")
        self.details = details or {}
        super().__init__(self.message)

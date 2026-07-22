"""Original PDF canonicalisation (verify, inspect, publish)."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from backend.app.canonical.errors import CanonicalisationError
from backend.app.canonical.models import CanonicalisationResult
from backend.app.canonical.service import CanonicalisationService
from backend.app.contracts.canonical import CanonicalisationMethod, CanonicalPageSourceType
from backend.app.contracts.errors import ErrorCode
from backend.app.settings.config import Settings


def canonicalise_original_pdf(
    *,
    settings: Settings,
    service: CanonicalisationService,
    session_id: str,
    document_id: str,
    job_id: str,
    original_path: Path,
    warnings: list[str] | None = None,
) -> CanonicalisationResult:
    """Verify an uploaded PDF and publish it as the canonical view."""

    _verify_pdf(original_path)
    staging_dir = service.staging_canonical_dir(session_id, job_id)
    staged_pdf = staging_dir / "source.pdf"
    service.link_or_copy(original_path, staged_pdf, chunk_bytes=settings.upload_chunk_bytes)
    try:
        return service.publish_atomic(
            session_id=session_id,
            document_id=document_id,
            staging_pdf=staged_pdf,
            method=CanonicalisationMethod.ORIGINAL_PDF,
            source_type=CanonicalPageSourceType.PDF,
            warnings=warnings,
        )
    finally:
        service.cleanup_staging(session_id, job_id)


def _verify_pdf(path: Path) -> None:
    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            raise CanonicalisationError(
                ErrorCode.UPLOAD_ENCRYPTED_PDF,
                "Encrypted PDFs cannot be canonicalised.",
            )
        if len(reader.pages) < 1:
            raise CanonicalisationError(
                ErrorCode.CANONICALISATION_INVALID_PDF,
                "The PDF has no readable pages.",
            )
    except CanonicalisationError:
        raise
    except (PdfReadError, OSError, ValueError, EOFError) as exc:
        raise CanonicalisationError(
            ErrorCode.CANONICALISATION_INVALID_PDF,
            "The PDF could not be read.",
        ) from exc

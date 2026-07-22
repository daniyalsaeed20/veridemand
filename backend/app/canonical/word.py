"""Word document canonicalisation via LibreOffice."""

from __future__ import annotations

from pathlib import Path

from backend.app.canonical.errors import CanonicalisationError
from backend.app.canonical.libreoffice import LibreOfficeService
from backend.app.canonical.models import CanonicalisationResult
from backend.app.canonical.service import CanonicalisationService
from backend.app.contracts.canonical import CanonicalisationMethod, CanonicalPageSourceType
from backend.app.contracts.documents import DocumentFormat
from backend.app.contracts.errors import ErrorCode
from backend.app.settings.config import Settings
from backend.app.uploads import word_validation


def recheck_word_safety(
    path: Path,
    fmt: DocumentFormat,
    settings: Settings,
    *,
    prior_warnings: list[str] | None = None,
) -> list[str]:
    """Re-run upload-time safety checks before conversion (macro/archive policy)."""

    warnings = list(prior_warnings or [])
    if fmt is DocumentFormat.DOCX:
        found = word_validation.validate_docx(path, settings)
        warnings.extend(found)
    elif fmt is DocumentFormat.DOC:
        word_validation.validate_doc(path)
    else:
        raise CanonicalisationError(
            ErrorCode.CANONICALISATION_FAILED,
            "Unsupported word format for canonicalisation.",
        )
    return warnings


def canonicalise_word_pdf(
    *,
    settings: Settings,
    service: CanonicalisationService,
    libreoffice: LibreOfficeService,
    session_id: str,
    document_id: str,
    job_id: str,
    original_path: Path,
    fmt: DocumentFormat,
    warnings: list[str] | None = None,
) -> CanonicalisationResult:
    """Convert DOC/DOCX to PDF with LibreOffice and publish atomically."""

    merged_warnings = recheck_word_safety(original_path, fmt, settings, prior_warnings=warnings)
    runtime = libreoffice.resolve()
    staging = service.staging_libreoffice_dir(session_id, job_id)
    # Workspace layout: input/, output/, profile/, temp/ under the job staging root.
    output_dir = staging / "output"
    converted = libreoffice.convert_to_pdf(
        original_path,
        output_dir=output_dir,
        profile_dir=staging,
    )
    try:
        return service.publish_atomic(
            session_id=session_id,
            document_id=document_id,
            staging_pdf=converted,
            method=CanonicalisationMethod.LIBREOFFICE_WRITER_PDF,
            source_type=CanonicalPageSourceType.WORD,
            warnings=merged_warnings,
            libreoffice_version=runtime.version,
        )
    finally:
        service.cleanup_staging(session_id, job_id)

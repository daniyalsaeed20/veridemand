"""DOCX → PDF conversion via LibreOffice headless (OD-05 option A)."""

from __future__ import annotations

import shutil
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

# Process-wide lock: prototype allows one LibreOffice conversion at a time.
_CONVERSION_LOCK = threading.Lock()


class ConversionError(Exception):
    """DOCX conversion failed (missing tool, timeout, or corrupt output)."""

    def __init__(self, message: str, *, error_code: str = "process_stage_failed") -> None:
        self.error_code = error_code
        super().__init__(message)


@dataclass(frozen=True)
class LibreOfficeConfig:
    executable: str = "soffice"
    timeout_seconds: int = 120


DocxConverter = Callable[[Path, Path, Path], Path]


def convert_docx_with_libreoffice(
    source_docx: Path,
    output_pdf: Path,
    work_dir: Path,
    *,
    config: LibreOfficeConfig | None = None,
) -> Path:
    """Convert DOCX to PDF under work_dir; move final PDF to output_pdf.

    Uses an application-controlled temporary directory. Deletes partial outputs
    on failure. Serializes conversions with a process-wide lock.
    """
    cfg = config or LibreOfficeConfig()
    work_dir.mkdir(parents=True, exist_ok=True)
    staging = work_dir / f"lo_{source_docx.stem}"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    staged_input = staging / source_docx.name
    produced: Path | None = None

    try:
        shutil.copy2(source_docx, staged_input)
        with _CONVERSION_LOCK:
            cmd = [
                cfg.executable,
                "--headless",
                "--nologo",
                "--nolockcheck",
                "--nodefault",
                "--norestore",
                "--convert-to",
                "pdf",
                "--outdir",
                str(staging),
                str(staged_input),
            ]
            try:
                completed = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=cfg.timeout_seconds,
                    check=False,
                    text=True,
                )
            except FileNotFoundError as exc:
                raise ConversionError(
                    "LibreOffice is not installed or LIBREOFFICE_PATH is invalid.",
                    error_code="process_stage_failed",
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise ConversionError(
                    "DOCX conversion timed out.",
                    error_code="process_stage_failed",
                ) from exc

            expected = staging / f"{staged_input.stem}.pdf"
            if completed.returncode != 0 or not expected.is_file() or expected.stat().st_size == 0:
                logger.warning(
                    "LibreOffice conversion failed",
                    extra={
                        "extra_fields": {
                            "returncode": completed.returncode,
                            "exc_type": "ConversionError",
                        }
                    },
                )
                raise ConversionError(
                    "DOCX conversion failed or produced an empty PDF.",
                    error_code="process_stage_failed",
                )
            produced = expected

        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        if output_pdf.exists():
            output_pdf.unlink()
        shutil.move(str(produced), str(output_pdf))
        produced = None
        return output_pdf
    except ConversionError:
        if output_pdf.exists():
            output_pdf.unlink(missing_ok=True)
        raise
    except Exception as exc:
        if output_pdf.exists():
            output_pdf.unlink(missing_ok=True)
        raise ConversionError(
            "DOCX conversion failed unexpectedly.",
            error_code="process_stage_failed",
        ) from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def fake_docx_converter_success(
    source_docx: Path,
    output_pdf: Path,
    work_dir: Path,
) -> Path:
    """Test adapter: write a minimal one-page PDF without LibreOffice."""
    from pypdf import PdfWriter

    work_dir.mkdir(parents=True, exist_ok=True)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with output_pdf.open("wb") as fh:
        writer.write(fh)
    # Touch source so callers that check existence stay honest
    _ = source_docx.is_file()
    return output_pdf


def fake_docx_converter_timeout(
    source_docx: Path,
    output_pdf: Path,
    work_dir: Path,
) -> Path:
    _ = (source_docx, work_dir)
    if output_pdf.exists():
        output_pdf.unlink(missing_ok=True)
    # Simulate a partial artifact then fail
    partial = work_dir / "partial_fail.pdf"
    work_dir.mkdir(parents=True, exist_ok=True)
    partial.write_bytes(b"%PDF-partial")
    partial.unlink(missing_ok=True)
    raise ConversionError("DOCX conversion timed out.", error_code="process_stage_failed")


def fake_docx_converter_failure(
    source_docx: Path,
    output_pdf: Path,
    work_dir: Path,
) -> Path:
    _ = (source_docx, work_dir)
    if output_pdf.exists():
        output_pdf.unlink(missing_ok=True)
    raise ConversionError(
        "LibreOffice is not installed or LIBREOFFICE_PATH is invalid.",
        error_code="process_stage_failed",
    )

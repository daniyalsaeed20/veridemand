"""Startup validation for the synthetic smoke corpus."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from scripts.smoke_corpus import EXPECTED_MANIFEST_SHA256, EXPECTED_PDF_SHA256
from scripts.smoke_corpus.paths import MANIFEST_PATH, PDF_PATH, README_PATH

PHASE_EXPECTATIONS = frozenset(
    {
        "current_phase_expected",
        "future_phase_expected",
        "not_yet_implemented",
        "viewer_only",
        "document_scoped_not_representable",
    }
)

_PRIVATE_BASENAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"srmc-sj", re.IGNORECASE),
    re.compile(r"wellstar-sj", re.IGNORECASE),
    re.compile(r"wellstar-ortho", re.IGNORECASE),
    re.compile(r"\bMR\s+\d{4,}\b", re.IGNORECASE),
    re.compile(r"MEDICAL\s+RECORDS", re.IGNORECASE),
    re.compile(r"Final Medical Records", re.IGNORECASE),
    re.compile(r"\bpatient\s+(?:id|name|dob)\b", re.IGNORECASE),
    re.compile(r"\bSSN\b"),
    re.compile(r"\bDOB:\s*\d", re.IGNORECASE),
)


@dataclass
class ValidationIssue:
    code: str
    message: str


@dataclass
class CorpusBundle:
    pdf_path: Path
    manifest_path: Path
    manifest: dict[str, Any]
    pdf_sha256: str
    manifest_sha256: str
    page_count: int
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_manifest(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("manifest root must be an object")
    return raw


def _readme_contains_checksums(readme: Path, pdf_sha: str, manifest_sha: str) -> bool:
    if not readme.is_file():
        return False
    text = readme.read_text(encoding="utf-8")
    return pdf_sha in text and manifest_sha in text


def _scan_pdf_text_for_private(reader: PdfReader) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            # pypdf may emit noisy warnings for synthetic emoji/CID pages.
            sink = io.StringIO()
            with contextlib.redirect_stderr(sink):
                text = page.extract_text() or ""
        except Exception:
            continue
        for pattern in _PRIVATE_BASENAME_PATTERNS:
            if pattern.search(text):
                issues.append(
                    ValidationIssue(
                        code="private_content_detected",
                        message=(
                            f"page {index} matched a private-corpus privacy heuristic "
                            f"(pattern={pattern.pattern!r}); details suppressed"
                        ),
                    )
                )
                break
    return issues


def validate_corpus(
    *,
    pdf_path: Path = PDF_PATH,
    manifest_path: Path = MANIFEST_PATH,
    readme_path: Path = README_PATH,
    expected_pdf_sha: str = EXPECTED_PDF_SHA256,
    expected_manifest_sha: str = EXPECTED_MANIFEST_SHA256,
    require_readme_checksums: bool = True,
) -> CorpusBundle:
    issues: list[ValidationIssue] = []

    if not pdf_path.is_file():
        issues.append(ValidationIssue("pdf_missing", f"PDF not found: {pdf_path}"))
    if not manifest_path.is_file():
        issues.append(ValidationIssue("manifest_missing", f"Manifest not found: {manifest_path}"))
    if issues:
        return CorpusBundle(
            pdf_path=pdf_path,
            manifest_path=manifest_path,
            manifest={},
            pdf_sha256="",
            manifest_sha256="",
            page_count=0,
            issues=issues,
        )

    pdf_sha = sha256_file(pdf_path)
    manifest_sha = sha256_file(manifest_path)
    if pdf_sha != expected_pdf_sha.upper():
        issues.append(
            ValidationIssue(
                "pdf_checksum_mismatch",
                "Committed PDF SHA-256 does not match the recorded checksum.",
            )
        )
    if manifest_sha != expected_manifest_sha.upper():
        issues.append(
            ValidationIssue(
                "manifest_checksum_mismatch",
                "Committed manifest SHA-256 does not match the recorded checksum.",
            )
        )
    if require_readme_checksums and not _readme_contains_checksums(
        readme_path, expected_pdf_sha.upper(), expected_manifest_sha.upper()
    ):
        issues.append(
            ValidationIssue(
                "readme_checksums_missing",
                "docs/smoke/README.md must record PDF and manifest SHA-256 values.",
            )
        )

    try:
        manifest = load_manifest(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issues.append(ValidationIssue("manifest_invalid", f"Cannot parse manifest: {exc}"))
        return CorpusBundle(
            pdf_path=pdf_path,
            manifest_path=manifest_path,
            manifest={},
            pdf_sha256=pdf_sha,
            manifest_sha256=manifest_sha,
            page_count=0,
            issues=issues,
        )

    privacy = manifest.get("privacy")
    if not isinstance(privacy, str) or "synthetic" not in privacy.lower():
        issues.append(
            ValidationIssue(
                "privacy_missing",
                "Manifest privacy field must declare synthetic non-private content.",
            )
        )

    try:
        reader = PdfReader(str(pdf_path))
        page_count = len(reader.pages)
    except Exception as exc:
        issues.append(ValidationIssue("pdf_unreadable", f"pypdf could not open PDF: {exc}"))
        return CorpusBundle(
            pdf_path=pdf_path,
            manifest_path=manifest_path,
            manifest=manifest,
            pdf_sha256=pdf_sha,
            manifest_sha256=manifest_sha,
            page_count=0,
            issues=issues,
        )

    expected_count = manifest.get("page_count_including_cover")
    if not isinstance(expected_count, int) or expected_count != page_count:
        issues.append(
            ValidationIssue(
                "page_count_mismatch",
                f"PDF has {page_count} pages; manifest page_count_including_cover="
                f"{expected_count!r}",
            )
        )

    pages = manifest.get("pages")
    if not isinstance(pages, list) or not pages:
        issues.append(ValidationIssue("pages_missing", "Manifest pages[] is empty or missing."))
        return CorpusBundle(
            pdf_path=pdf_path,
            manifest_path=manifest_path,
            manifest=manifest,
            pdf_sha256=pdf_sha,
            manifest_sha256=manifest_sha,
            page_count=page_count,
            issues=issues,
        )

    seen_ids: set[str] = set()
    for entry in pages:
        if not isinstance(entry, dict):
            issues.append(
                ValidationIssue("page_entry_invalid", "A pages[] entry is not an object.")
            )
            continue
        test_id = entry.get("test_id")
        page_number = entry.get("page_number")
        phase = entry.get("phase_expectation")
        source_mode = entry.get("expected_source_mode")
        viewer = entry.get("expected_viewer")
        canonical_viewer = entry.get("canonical_viewer_success")

        if not isinstance(test_id, str) or not test_id:
            issues.append(ValidationIssue("test_id_missing", "A page is missing test_id."))
        elif test_id in seen_ids:
            issues.append(ValidationIssue("duplicate_test_id", f"Duplicate test_id {test_id!r}."))
        else:
            seen_ids.add(test_id)

        if not isinstance(page_number, int) or page_number < 1 or page_number > page_count:
            issues.append(
                ValidationIssue(
                    "missing_page",
                    f"test_id={test_id!r} page_number={page_number!r} is outside 1..{page_count}.",
                )
            )

        if phase not in PHASE_EXPECTATIONS:
            issues.append(
                ValidationIssue(
                    "phase_expectation_invalid",
                    f"test_id={test_id!r} has invalid phase_expectation={phase!r}.",
                )
            )

        has_authority = isinstance(source_mode, str) and bool(source_mode)
        has_viewer = (
            (isinstance(viewer, str) and bool(viewer))
            or canonical_viewer is True
            or phase == "viewer_only"
        )
        if not has_authority and not has_viewer:
            issues.append(
                ValidationIssue(
                    "outcome_missing",
                    f"test_id={test_id!r} needs expected_source_mode or a viewer outcome.",
                )
            )

    issues.extend(_scan_pdf_text_for_private(reader))

    return CorpusBundle(
        pdf_path=pdf_path,
        manifest_path=manifest_path,
        manifest=manifest,
        pdf_sha256=pdf_sha,
        manifest_sha256=manifest_sha,
        page_count=page_count,
        issues=issues,
    )

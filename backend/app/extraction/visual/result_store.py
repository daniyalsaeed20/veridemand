"""Atomic publish helpers for visual OCR page and document results."""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.visual import VisualDocumentSummary, VisualPageResult
from backend.app.extraction.visual.errors import VisualOcrError

logger = logging.getLogger("veridemand.visual.result_store")


def page_filename(page_number: int) -> str:
    return f"page-{page_number:04d}.json"


def write_page_atomic(output_dir: Path, page: VisualPageResult) -> Path:
    """Validate and atomically publish one page result JSON."""

    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / page_filename(page.page_number)
    part_path = final_path.with_suffix(final_path.suffix + ".part")
    try:
        payload = page.model_dump(mode="json")
        # Re-validate round-trip to catch contract drift before publish.
        VisualPageResult.model_validate(payload)
        part_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        os.replace(part_path, final_path)
        return final_path
    except VisualOcrError:
        raise
    except Exception as exc:
        if part_path.exists():
            part_path.unlink(missing_ok=True)
        raise VisualOcrError(
            ErrorCode.VISUAL_RESULT_PUBLISH_FAILED,
            "Failed to publish visual page result.",
            operation="write_page_atomic",
            failing_component="result_store",
            page_number=page.page_number,
            exception_type=type(exc).__name__,
        ) from exc


def write_summary_atomic(output_dir: Path, summary: VisualDocumentSummary) -> Path:
    """Validate and atomically publish the document visual summary."""

    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / "summary.json"
    part_path = final_path.with_suffix(final_path.suffix + ".part")
    try:
        payload = summary.model_dump(mode="json")
        VisualDocumentSummary.model_validate(payload)
        part_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        os.replace(part_path, final_path)
        return final_path
    except Exception as exc:
        if part_path.exists():
            part_path.unlink(missing_ok=True)
        raise VisualOcrError(
            ErrorCode.VISUAL_RESULT_PUBLISH_FAILED,
            "Failed to publish visual document summary.",
            operation="write_summary_atomic",
            failing_component="result_store",
            exception_type=type(exc).__name__,
        ) from exc


def promote_results_dir(*, results_part: Path, results_final: Path) -> None:
    """Atomically replace the published visual results directory."""

    parent = results_final.parent
    parent.mkdir(parents=True, exist_ok=True)
    backup = parent / f"{results_final.name}.bak"
    try:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        if results_final.exists():
            os.replace(results_final, backup)
        os.replace(results_part, results_final)
        shutil.rmtree(backup, ignore_errors=True)
    except Exception as exc:
        raise VisualOcrError(
            ErrorCode.VISUAL_RESULT_PUBLISH_FAILED,
            "Failed to promote visual results directory.",
            operation="promote_results_dir",
            failing_component="result_store",
            exception_type=type(exc).__name__,
        ) from exc


def list_published_page_numbers(output_dir: Path) -> list[int]:
    """Return sorted page numbers that already have published page JSON files."""

    if not output_dir.is_dir():
        return []
    pages: list[int] = []
    for path in output_dir.glob("page-*.json"):
        if path.name.endswith(".part"):
            continue
        stem = path.stem  # page-0001
        try:
            pages.append(int(stem.split("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return sorted(pages)


def load_page(output_dir: Path, page_number: int) -> VisualPageResult | None:
    path = output_dir / page_filename(page_number)
    if not path.is_file():
        return None
    return VisualPageResult.model_validate_json(path.read_text(encoding="utf-8"))


def load_summary(output_dir: Path) -> VisualDocumentSummary | None:
    path = output_dir / "summary.json"
    if not path.is_file():
        return None
    return VisualDocumentSummary.model_validate_json(path.read_text(encoding="utf-8"))


def remove_incomplete_page_parts(output_dir: Path) -> None:
    """Delete any ``*.json.part`` files left by a crashed publish."""

    if not output_dir.is_dir():
        return
    for path in output_dir.glob("*.json.part"):
        path.unlink(missing_ok=True)


# Aliases used by VisualOcrService.
def publish_page_atomic(page: VisualPageResult, output_dir: Path) -> Path:
    return write_page_atomic(output_dir, page)


def publish_summary_atomic(summary: VisualDocumentSummary, output_dir: Path) -> Path:
    return write_summary_atomic(output_dir, summary)


def cleanup_staging(staging_dir: Path) -> None:
    shutil.rmtree(staging_dir, ignore_errors=True)


def delete_results(results_dir: Path) -> None:
    shutil.rmtree(results_dir, ignore_errors=True)
    part = results_dir.with_name(f"{results_dir.name}.part")
    shutil.rmtree(part, ignore_errors=True)

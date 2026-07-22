"""Unit tests for visual result store atomic publish."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from backend.app.contracts.native import SourceMode
from backend.app.contracts.visual import (
    VisualDocumentSummary,
    VisualPageResult,
    VisualPageStatus,
    VisualProcessingStatus,
    VisualProgress,
)
from backend.app.extraction.visual.result_store import (
    load_page,
    load_summary,
    write_page_atomic,
    write_summary_atomic,
)


def test_write_and_load_page_atomic(tmp_path: Path) -> None:
    page = VisualPageResult(
        page_number=1,
        status=VisualPageStatus.COMPLETED_NO_TEXT,
        source_mode=SourceMode.VISUAL_AUTHORITY,
        visual_result_available=False,
        visual_processing_attempted=True,
    )
    path = write_page_atomic(tmp_path, page)
    assert path.name == "page-0001.json"
    assert not path.with_suffix(path.suffix + ".part").exists()
    loaded = load_page(tmp_path, 1)
    assert loaded is not None
    assert loaded.page_number == 1
    assert loaded.status is VisualPageStatus.COMPLETED_NO_TEXT


def test_write_and_load_summary_atomic(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    summary = VisualDocumentSummary(
        document_id="doc_" + "a" * 32,
        visual_processing_status=VisualProcessingStatus.VISUAL_PROCESSING_COMPLETE,
        page_count=1,
        pages_selected=0,
        pages_completed=0,
        pages_no_text=0,
        pages_failed=0,
        pages_cancelled=0,
        native_pages_retained=1,
        native_pages_downgraded=0,
        visual_result_available=False,
        handwriting_assessment_pending=True,
        final_result_available=False,
        progress=VisualProgress(percent=65, pages_completed=1, pages_total=1),
        created_at=now,
        completed_at=now,
    )
    path = write_summary_atomic(tmp_path, summary)
    assert path.name == "summary.json"
    loaded = load_summary(tmp_path)
    assert loaded is not None
    assert loaded.page_count == 1
    assert loaded.visual_processing_status is VisualProcessingStatus.VISUAL_PROCESSING_COMPLETE

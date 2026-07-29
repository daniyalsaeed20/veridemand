"""Coordinator ↔ VisualOcrService admission contract (Checkpoint B)."""

from __future__ import annotations

from backend.app.processing.fair_scheduler import (
    FairDocumentScheduler,
    SchedulerConfig,
    SchedulerWorkUnit,
    WorkClass,
    _new_work_unit_id,
)


def _admit_like_coordinator(
    *,
    payload: dict[str, object],
    page_count: int,
    fair_enabled: bool = True,
) -> FairDocumentScheduler | None:
    """Mirror the coordinator visual_pages_selected admission gate."""
    selected_page_numbers: list[int] = []
    page_numbers = payload.get("page_numbers")
    if isinstance(page_numbers, list):
        selected_page_numbers = [
            int(p) for p in page_numbers if isinstance(p, (int, float, str))
        ]
    full_raw = payload.get("full_ocr_pages_selected")
    full_ocr_pages_selected = int(full_raw) if isinstance(full_raw, (int, float)) else 0

    if not (fair_enabled and full_ocr_pages_selected > 0 and selected_page_numbers):
        return None

    sched = FairDocumentScheduler(SchedulerConfig(enabled=True, page_quantum=2))
    units = [
        SchedulerWorkUnit(
            work_unit_id=_new_work_unit_id(),
            session_id="ses_test",
            document_id="doc_test",
            route="full_visual_ocr",
            work_class=WorkClass.FULL_OCR_PAGE,
            document_page_number=page_num,
            document_pages_total=page_count,
            selected_page_index=idx,
            selected_pages_total=full_ocr_pages_selected,
        )
        for idx, page_num in enumerate(selected_page_numbers, 1)
    ]
    sched.admit_document("doc_test", "ses_test", units)
    claimed = sched.next_work_unit()
    assert claimed is not None
    assert claimed[0].document_id == "doc_test"
    return sched


def test_admission_requires_page_numbers() -> None:
    """Legacy payload without page_numbers must not admit (pre-Checkpoint-B bug)."""
    payload = {
        "type": "visual_pages_selected",
        "pages_selected": 2,
        "full_ocr_pages_selected": 2,
    }
    assert _admit_like_coordinator(payload=payload, page_count=10) is None


def test_admission_with_page_numbers() -> None:
    """VisualOcrService page_numbers list drives live scheduler admission."""
    payload = {
        "type": "visual_pages_selected",
        "pages_selected": 3,
        "page_numbers": [2, 5, 9],
        "full_ocr_pages_selected": 3,
    }
    sched = _admit_like_coordinator(payload=payload, page_count=12)
    assert sched is not None
    doc = sched.get_document("doc_test")
    assert doc is not None
    assert doc.remaining_work == 3
    assert sched.active_document_id == "doc_test"
    assert sched.turn_number >= 1


def test_admission_skipped_when_fair_disabled() -> None:
    payload = {
        "page_numbers": [1, 2],
        "full_ocr_pages_selected": 2,
    }
    assert _admit_like_coordinator(payload=payload, page_count=2, fair_enabled=False) is None


def test_admission_skipped_for_native_only() -> None:
    payload = {
        "page_numbers": [],
        "pages_selected": 0,
        "full_ocr_pages_selected": 0,
    }
    assert _admit_like_coordinator(payload=payload, page_count=97) is None


def test_visual_service_emits_page_numbers_field() -> None:
    """Source contract: VisualOcrService progress payload includes page_numbers."""
    from pathlib import Path

    source = Path("backend/app/extraction/visual/service.py").read_text(encoding="utf-8")
    assert '"page_numbers": list(selected)' in source
    assert '"type": "visual_pages_selected"' in source

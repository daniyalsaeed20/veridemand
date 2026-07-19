"""Deterministic PDFium serialization tests (B-01) — barriers/spies, not sleeps."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.services.documents import pdfium_runtime
from app.services.documents.thumbnails import ThumbnailError, count_pdf_pages, create_thumbnails


def _blank_pdf(path: Path, pages: int = 3) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


@pytest.fixture(autouse=True)
def _clear_hooks() -> None:
    pdfium_runtime.set_test_hooks()
    pdfium_runtime.reset_inflight_stats()
    yield
    pdfium_runtime.set_test_hooks()
    pdfium_runtime.reset_inflight_stats()


def test_concurrent_thumbnails_serialize_critical_section(tmp_path: Path) -> None:
    a = _blank_pdf(tmp_path / "a.pdf", 4)
    b = _blank_pdf(tmp_path / "b.pdf", 4)
    # Barrier OUTSIDE the lock so both threads contend together (no deadlock).
    ready = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker(src: Path, out: Path) -> None:
        try:
            ready.wait(timeout=5)
            create_thumbnails(src, out, max_width=80)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    pdfium_runtime.reset_inflight_stats()
    t1 = threading.Thread(target=worker, args=(a, tmp_path / "thumbs_a"))
    t2 = threading.Thread(target=worker, args=(b, tmp_path / "thumbs_b"))
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    assert errors == []
    assert pdfium_runtime.get_max_inflight() == 1
    assert (tmp_path / "thumbs_a" / "page_1.png").is_file()
    assert (tmp_path / "thumbs_b" / "page_1.png").is_file()


def test_count_overlaps_render_serialized(tmp_path: Path) -> None:
    pdf = _blank_pdf(tmp_path / "c.pdf", 3)
    ready = threading.Barrier(2)
    pdfium_runtime.reset_inflight_stats()
    results: list[object] = []
    errors: list[BaseException] = []

    def count_worker() -> None:
        try:
            ready.wait(timeout=5)
            results.append(("count", count_pdf_pages(pdf)))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def render_worker() -> None:
        try:
            ready.wait(timeout=5)
            create_thumbnails(pdf, tmp_path / "thumbs_c", max_width=64)
            results.append(("thumbs", True))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=count_worker)
    t2 = threading.Thread(target=render_worker)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    assert errors == []
    assert len(results) == 2
    assert pdfium_runtime.get_max_inflight() == 1


def test_exception_releases_mutex_and_subsequent_work_succeeds(tmp_path: Path) -> None:
    pdf = _blank_pdf(tmp_path / "d.pdf", 2)
    calls = {"n": 0}

    def fault(op: str) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError(f"injected_fault:{op}")

    pdfium_runtime.set_test_hooks(fault=fault)
    with pytest.raises(ThumbnailError):
        create_thumbnails(pdf, tmp_path / "thumbs_fail", max_width=64)

    pdfium_runtime.set_test_hooks()
    paths = create_thumbnails(pdf, tmp_path / "thumbs_ok", max_width=64)
    assert len(paths) == 2
    assert count_pdf_pages(pdf) == 2


def test_cancel_simulation_does_not_permanently_lock(tmp_path: Path) -> None:
    """Simulate cancelled work via injected exception mid-critical-section."""
    pdf = _blank_pdf(tmp_path / "e.pdf", 2)

    def fault(_op: str) -> None:
        raise InterruptedError("cancelled")

    pdfium_runtime.set_test_hooks(fault=fault)
    with pytest.raises(InterruptedError):
        pdfium_runtime.count_pages(pdf)

    pdfium_runtime.set_test_hooks()
    assert pdfium_runtime.count_pages(pdf) == 2


def test_separate_callers_share_same_mutex(tmp_path: Path) -> None:
    lock_a = pdfium_runtime.get_pdfium_lock()
    lock_b = pdfium_runtime.get_pdfium_lock()
    assert lock_a is lock_b
    pdf = _blank_pdf(tmp_path / "f.pdf", 1)
    assert count_pdf_pages(pdf) == 1
    assert pdfium_runtime.count_pages(pdf) == 1


def test_max_inflight_exactly_one_under_four_way_contention(tmp_path: Path) -> None:
    pdfs = [_blank_pdf(tmp_path / f"p{i}.pdf", 2) for i in range(4)]
    ready = threading.Barrier(4)
    errors: list[BaseException] = []
    pdfium_runtime.reset_inflight_stats()

    def worker(i: int) -> None:
        try:
            ready.wait(timeout=5)
            if i % 2 == 0:
                count_pdf_pages(pdfs[i])
            else:
                create_thumbnails(pdfs[i], tmp_path / f"out{i}", max_width=48)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == []
    assert pdfium_runtime.get_max_inflight() == 1

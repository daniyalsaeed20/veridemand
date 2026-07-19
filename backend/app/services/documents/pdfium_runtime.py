"""Process-wide PDFium/pypdfium2 runtime boundary (Phase 2 hardening B-01).

Only this module may import pypdfium2 in application code. All open/render/count
operations run under a single process-wide RLock so concurrent request threads
cannot enter PDFium simultaneously.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

# Process-wide: shared by every service instance / session / document.
_PDFIUM_LOCK = threading.RLock()

# Test instrumentation (barrier/spy). Production leaves these unset.
_enter_hook: Callable[[], None] | None = None
_exit_hook: Callable[[], None] | None = None
_fault_hook: Callable[[str], None] | None = None

# Observability for concurrency tests (safe; no document content).
_inflight = 0
_max_inflight = 0
_inflight_lock = threading.Lock()


class PdfiumRuntimeError(Exception):
    """PDFium operation failed (open, count, or render)."""


@dataclass(frozen=True)
class RenderedPageImage:
    """PIL image produced under the PDFium lock; native handles already closed."""

    image: Image.Image
    page_index: int  # 0-based


def get_pdfium_lock() -> threading.RLock:
    """Expose the process-wide lock identity for tests (do not use for nesting)."""
    return _PDFIUM_LOCK


def reset_inflight_stats() -> None:
    global _inflight, _max_inflight
    with _inflight_lock:
        _inflight = 0
        _max_inflight = 0


def get_max_inflight() -> int:
    with _inflight_lock:
        return _max_inflight


def set_test_hooks(
    *,
    enter: Callable[[], None] | None = None,
    exit_hook: Callable[[], None] | None = None,
    fault: Callable[[str], None] | None = None,
) -> None:
    """Install optional test hooks. Pass all-None to clear."""
    global _enter_hook, _exit_hook, _fault_hook
    _enter_hook = enter
    _exit_hook = exit_hook
    _fault_hook = fault


@contextmanager
def _critical_section(op_name: str) -> Iterator[None]:
    global _inflight, _max_inflight
    with _PDFIUM_LOCK:
        with _inflight_lock:
            _inflight += 1
            if _inflight > _max_inflight:
                _max_inflight = _inflight
        if _enter_hook is not None:
            _enter_hook()
        try:
            if _fault_hook is not None:
                _fault_hook(op_name)
            yield
        finally:
            with _inflight_lock:
                _inflight -= 1
            if _exit_hook is not None:
                _exit_hook()


def count_pages(canonical_pdf: Path) -> int:
    """Return page count. Native PdfDocument never escapes this function."""
    with _critical_section("count_pages"):
        pdf = pdfium.PdfDocument(str(canonical_pdf))
        try:
            return len(pdf)
        finally:
            pdf.close()


def render_all_pages(
    canonical_pdf: Path,
    *,
    scale: float = 1.0,
) -> list[RenderedPageImage]:
    """Render every page to PIL images under the lock; close all native resources."""
    rendered: list[RenderedPageImage] = []
    with _critical_section("render_all_pages"):
        pdf = pdfium.PdfDocument(str(canonical_pdf))
        try:
            for index in range(len(pdf)):
                page = pdf[index]
                try:
                    bitmap = page.render(scale=scale)
                    pil = bitmap.to_pil()
                    # Copy so bitmap/page teardown cannot invalidate caller pixels.
                    rendered.append(RenderedPageImage(image=pil.copy(), page_index=index))
                    pil.close()
                finally:
                    page.close()
        finally:
            pdf.close()
    return rendered


def render_page(
    canonical_pdf: Path,
    *,
    page_index: int,
    scale: float = 1.0,
) -> Image.Image:
    """Render one 0-based page to a detached PIL image."""
    with _critical_section("render_page"):
        pdf = pdfium.PdfDocument(str(canonical_pdf))
        try:
            if page_index < 0 or page_index >= len(pdf):
                raise PdfiumRuntimeError(f"page_index out of range: {page_index}")
            page = pdf[page_index]
            try:
                bitmap = page.render(scale=scale)
                pil = bitmap.to_pil()
                copied: Image.Image = pil.copy()
                pil.close()
                return copied
            finally:
                page.close()
        finally:
            pdf.close()

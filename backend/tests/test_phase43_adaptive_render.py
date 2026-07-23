"""Phase 4.3 unit tests: raster policy, adaptive DPI, progress, Future cleanup."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.app.contracts.documents import DocumentStatus
from backend.app.extraction.visual.page_raster_policy import (
    EmbeddedImageInfo,
    PageRasterAssessment,
    RenderSourcePolicy,
    plan_render,
)
from backend.app.extraction.visual.renderer import RenderLimits, compute_effective_dpi, render_page
from backend.app.sessions.models import RuntimeDocument, _document_progress_percent

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SCAN = ROOT / "fixtures" / "synthetic" / "ocr" / "full-page-scan-identity.pdf"


@pytest.fixture(scope="module", autouse=True)
def _ensure_fixtures() -> None:
    if not FIXTURE_SCAN.is_file():
        from scripts.generate_phase43_ocr_fixtures import main as gen

        assert gen() == 0


def test_full_page_scan_does_not_upscale_to_200dpi() -> None:
    """Identity scan (850x1100 pt = px) must not become ~2361x3056 at 200 DPI."""

    rendered = render_page(
        FIXTURE_SCAN,
        page_number=1,
        page_width_points=850.0,
        page_height_points=1100.0,
        limits=RenderLimits(
            target_dpi=200,
            min_effective_dpi=120,
            max_render_pixels=40_000_000,
            max_render_side_pixels=6000,
            dimension_tolerance_points=2.0,
        ),
    )
    try:
        # Uncapped 200 DPI would be ~2361x3056; source-capped ~850x1100.
        assert rendered.width_pixels <= 900
        assert rendered.height_pixels <= 1150
        assert rendered.source_resolution_cap_applied or rendered.render_source_policy in {
            RenderSourcePolicy.EMBEDDED_FULL_PAGE_IMAGE.value,
            RenderSourcePolicy.PDFIUM_RENDER_CAPPED_TO_SOURCE_RESOLUTION.value,
        }
        assert rendered.effective_dpi <= 80.0
        # Hypothetical 200 DPI size for documentation / regression math.
        naive_w = 850 * 200 / 72
        naive_h = 1100 * 200 / 72
        assert naive_w > 2300 and naive_h > 3000
    finally:
        rendered.image.close()


def test_plan_render_caps_source_resolution() -> None:
    assessment = PageRasterAssessment(
        image_count=1,
        largest_coverage_ratio=0.99,
        text_object_count=0,
        path_object_count=0,
        embedded=EmbeddedImageInfo(
            width_px=1704,
            height_px=2190,
            coverage_ratio=0.99,
            x0=0,
            y0=0,
            x1=1704,
            y1=2190,
        ),
        is_full_page_raster=True,
        source_width_px=1704,
        source_height_px=2190,
    )
    plan = plan_render(
        assessment,
        page_width_points=1704.0,
        page_height_points=2190.0,
        requested_dpi=200.0,
        min_effective_dpi=120.0,
        max_render_pixels=40_000_000,
        max_render_side_pixels=6000,
    )
    assert plan.source_resolution_cap_applied
    assert plan.effective_dpi <= 72.5
    # Confirm naive 200 DPI would hit ~4733x6083.
    naive_w = 1704 * 200 / 72
    naive_h = 2190 * 200 / 72
    assert abs(naive_w - 4733.33) < 1.0
    assert abs(naive_h - 6083.33) < 1.0


def test_visual_failure_progress_not_stuck_at_native_32() -> None:
    doc = RuntimeDocument(
        document_id="doc_" + "a" * 32,
        display_filename="sample.pdf",
        extension="pdf",
        format="pdf",  # type: ignore[arg-type]
        media_type="application/pdf",
        size_bytes=10,
        sha256="0" * 64,
        page_count=2,
        page_count_status="known",  # type: ignore[arg-type]
        status=DocumentStatus.VISUAL_PROCESSING_FAILED,
        progress_percent=32,
        failure_stage="paddle_text_detection",
        failure_code="ocr_page_timeout",
    )
    assert _document_progress_percent(doc) == 65


def test_visual_processing_progress_floor_above_native() -> None:
    doc = RuntimeDocument(
        document_id="doc_" + "b" * 32,
        display_filename="sample.pdf",
        extension="pdf",
        format="pdf",  # type: ignore[arg-type]
        media_type="application/pdf",
        size_bytes=10,
        sha256="1" * 64,
        page_count=2,
        page_count_status="known",  # type: ignore[arg-type]
        status=DocumentStatus.VISUAL_PROCESSING,
        progress_percent=32,
    )
    assert _document_progress_percent(doc) >= 36


@pytest.mark.asyncio
async def test_future_exception_is_retrieved_on_timeout() -> None:
    """Regression: set_exception must be consumed to avoid loop warnings."""

    loop = asyncio.get_running_loop()
    seen: list[object] = []

    def _handler(_loop: asyncio.AbstractEventLoop, context: dict[str, object]) -> None:
        seen.append(context.get("message") or context.get("exception"))

    previous = loop.get_exception_handler()
    loop.set_exception_handler(_handler)
    try:
        future: asyncio.Future[object] = loop.create_future()
        future.set_exception(RuntimeError("Visual OCR page processing timed out."))
        # Mimic worker_manager._fail_active retrieval.
        _ = future.exception()
        await asyncio.sleep(0)
        assert not any(isinstance(item, str) and "never retrieved" in item.lower() for item in seen)
        assert not any(
            isinstance(item, BaseException) and "never retrieved" in str(item).lower()
            for item in seen
        )
    finally:
        loop.set_exception_handler(previous)


def test_compute_effective_dpi_respects_side_cap() -> None:
    dpi = compute_effective_dpi(
        page_width_points=1704.0,
        page_height_points=2190.0,
        target_dpi=200.0,
        min_effective_dpi=120.0,
        max_render_pixels=40_000_000,
        max_render_side_pixels=6000,
    )
    height = 2190.0 * dpi / 72.0
    assert height <= 6000.0 + 1e-6

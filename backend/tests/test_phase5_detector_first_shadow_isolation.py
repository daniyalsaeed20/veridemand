"""Shadow isolation — detector-first path stays off the live Phase 4 worker."""

from __future__ import annotations

from pathlib import Path

from backend.app.contracts.documents import MAX_PHASE4_PROGRESS_PERCENT
from backend.app.processing.progress_weights import OVERALL_CAP
from backend.app.settings.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_detect_first_shadow_default_off() -> None:
    settings = Settings()
    assert settings.phase5_detect_first_shadow_enabled is False
    assert settings.handwriting_router_enabled is False


def test_progress_cap_still_65() -> None:
    assert OVERALL_CAP == 65.0
    assert MAX_PHASE4_PROGRESS_PERCENT == 65


def test_worker_does_not_call_detect_first_apis() -> None:
    text = (ROOT / "backend/app/extraction/visual/worker.py").read_text(encoding="utf-8")
    assert "detect_text" not in text
    assert "recognise_text_crops" not in text
    assert "load_detect_first_modules" not in text
    assert "handwriting_router" not in text


def test_combined_recognise_surface_preserved() -> None:
    text = (ROOT / "backend/app/extraction/visual/paddle_adapter.py").read_text(encoding="utf-8")
    assert "def recognise(" in text
    assert "def detect_text(" in text
    assert "def recognise_text_crops(" in text
    assert "self._ocr.predict" in text
    # Combined load must not initialise detect-first modules.
    load_block = text.split("def load(self)", 1)[1].split("def _synthetic_image", 1)[0]
    assert "create_model" not in load_block
    assert "load_detect_first_modules" not in load_block


def test_service_repair_callbacks_unchanged_combined_helpers() -> None:
    text = (ROOT / "backend/app/extraction/visual/service.py").read_text(encoding="utf-8")
    assert "recognise_only" in text
    assert "detect_and_recognise_crop" in text
    assert "detect_text" not in text
    assert "recognise_text_crops" not in text


def test_health_does_not_require_detect_first() -> None:
    text = (ROOT / "backend/app/health/service.py").read_text(encoding="utf-8")
    assert "detect_first" not in text
    assert "phase5_detect_first" not in text


def test_fair_scheduling_setting_defaults_unchanged() -> None:
    settings = Settings()
    assert settings.fair_ocr_scheduling_enabled is True
    assert settings.fair_ocr_page_quantum == 2
    assert settings.hybrid_page_routing_enabled is True


def test_corpus_script_not_imported_by_app_startup() -> None:
    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    assert "build_detector_first_corpus" not in main
    assert "detector_first" not in main

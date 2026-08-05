"""Unit tests for detector-first Paddle adapter helpers (mocked modules)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PIL import Image, ImageDraw

from backend.app.extraction.visual.detect_first_types import DetectedTextRegion
from backend.app.extraction.visual.models import OcrRuntimeConfig
from backend.app.extraction.visual.paddle_adapter import (
    PaddleOcrAdapter,
    _build_detected_region,
    _classify_recognition_status,
    _paddlex_result_dict,
    _stable_region_id,
)


def _synth_page() -> Image.Image:
    image = Image.new("RGB", (200, 80), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 20, 90, 50), fill=(0, 0, 0))
    return image


def test_stable_region_id_deterministic() -> None:
    poly = ((0.1, 0.2), (0.4, 0.2), (0.4, 0.3), (0.1, 0.3))
    a = _stable_region_id(page_index=0, order_index=1, polygon_norm=poly)
    b = _stable_region_id(page_index=0, order_index=1, polygon_norm=poly)
    assert a == b
    assert a.startswith("dfreg_")


def test_build_detected_region_normalised_geometry() -> None:
    region = _build_detected_region(
        poly_px=[(10.0, 20.0), (90.0, 20.0), (90.0, 50.0), (10.0, 50.0)],
        score=0.91,
        page_index=2,
        order_index=0,
        width_px=200,
        height_px=100,
        detector_model_name="PP-OCRv5_mobile_det",
        detector_version="3.7.2",
    )
    assert isinstance(region, DetectedTextRegion)
    assert region.page_index == 2
    assert region.order_index == 0
    assert 0.0 <= region.bbox_norm[0] <= 1.0
    assert region.detection_confidence == pytest.approx(0.91)
    assert not hasattr(region, "text")


def test_build_detected_region_rejects_degenerate() -> None:
    with pytest.raises(ValueError):
        _build_detected_region(
            poly_px=[(1.0, 1.0), (2.0, 1.0)],
            score=0.5,
            page_index=0,
            order_index=0,
            width_px=100,
            height_px=100,
            detector_model_name="PP-OCRv5_mobile_det",
            detector_version=None,
        )


def test_classify_recognition_status() -> None:
    assert (
        _classify_recognition_status(text="", confidence=0.9, low_thr=0.75, min_thr=0.3) == "empty"
    )
    assert (
        _classify_recognition_status(text="a", confidence=0.2, low_thr=0.75, min_thr=0.3)
        == "rejected"
    )
    assert (
        _classify_recognition_status(text="a", confidence=0.5, low_thr=0.75, min_thr=0.3)
        == "low_confidence"
    )
    assert (
        _classify_recognition_status(text="a", confidence=0.9, low_thr=0.75, min_thr=0.3)
        == "recognised"
    )


def test_paddlex_result_dict_unwraps_res() -> None:
    class _Res:
        def __init__(self) -> None:
            self.json = {
                "res": {"dt_polys": [[[0, 0], [1, 0], [1, 1], [0, 1]]], "dt_scores": [0.8]}
            }

    assert _paddlex_result_dict([_Res()]) == {
        "dt_polys": [[[0, 0], [1, 0], [1, 1], [0, 1]]],
        "dt_scores": [0.8],
    }


def test_detect_text_does_not_call_recognizer() -> None:
    adapter = PaddleOcrAdapter(OcrRuntimeConfig())
    det = MagicMock()
    rec = MagicMock()

    class _DetResult:
        def __init__(self) -> None:
            self.json = {
                "res": {
                    "dt_polys": [
                        [[10, 20], [90, 20], [90, 50], [10, 50]],
                        [[100, 10], [180, 10], [180, 40], [100, 40]],
                    ],
                    "dt_scores": [0.95, 0.80],
                }
            }

    det.predict.return_value = [_DetResult()]
    adapter._det_model = det
    adapter._rec_model = rec
    adapter._paddlex_version = "3.7.2"

    regions = adapter.detect_text(_synth_page(), page_index=0)
    assert len(regions) == 2
    assert regions[0].order_index == 0
    assert regions[1].order_index == 1
    det.predict.assert_called_once()
    rec.predict.assert_not_called()


def test_recognise_text_crops_no_redetection() -> None:
    adapter = PaddleOcrAdapter(
        OcrRuntimeConfig(ocr_min_recognition_score=0.3, ocr_low_confidence_score=0.75)
    )
    det = MagicMock()
    rec = MagicMock()

    class _RecResult:
        def __init__(self, text: str, score: float) -> None:
            self.json = {"res": {"rec_text": text, "rec_score": score}}

    rec.predict.side_effect = [
        [_RecResult("hello", 0.92)],
        [_RecResult("", 0.1)],
        [_RecResult("x", 0.5)],
        Exception("boom"),
    ]
    adapter._det_model = det
    adapter._rec_model = rec
    adapter._paddlex_version = "3.7.2"

    crop = Image.new("RGB", (40, 20), color=(255, 255, 255))
    results = adapter.recognise_text_crops(
        [
            ("r1", crop),
            ("r2", crop),
            ("r3", crop),
            ("r4", crop),
        ]
    )
    assert [r.region_id for r in results] == ["r1", "r2", "r3", "r4"]
    assert results[0].status == "recognised"
    assert results[1].status == "empty"
    assert results[2].status == "low_confidence"
    assert results[3].status == "failed"
    det.predict.assert_not_called()
    assert rec.predict.call_count == 4


def test_detect_first_not_loaded_by_default() -> None:
    from backend.app.extraction.visual.errors import VisualOcrError

    adapter = PaddleOcrAdapter(OcrRuntimeConfig())
    assert adapter.detect_first_loaded is False
    with pytest.raises(VisualOcrError):
        adapter.detect_text(_synth_page())


def test_batched_recognition_preserves_order() -> None:
    adapter = PaddleOcrAdapter(OcrRuntimeConfig())

    class _RecResult:
        def __init__(self, text: str) -> None:
            self.json = {"res": {"rec_text": text, "rec_score": 0.99}}

    rec = MagicMock()
    rec.predict.side_effect = [[_RecResult(f"t{i}")] for i in range(5)]
    adapter._rec_model = rec
    adapter._det_model = MagicMock()
    crop = Image.new("RGB", (16, 16), (255, 255, 255))
    results = adapter.recognise_text_crops([(f"id{i}", crop) for i in range(5)], batch_size=2)
    assert [r.region_id for r in results] == [f"id{i}" for i in range(5)]
    assert all(r.status == "recognised" for r in results)

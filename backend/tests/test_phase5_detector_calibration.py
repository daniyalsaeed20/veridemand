"""Phase 5 Task C1 — bounded detector calibration contracts."""

from __future__ import annotations

import pytest

from backend.app.contracts.geometry import NormalisedBoundingBox
from backend.app.datasets.phase5.constants import (
    DETECTOR_CALIBRATION_MAX_CONFIGS,
    DETECTOR_DEFAULT_BOX_THRESH,
    DETECTOR_DEFAULT_LIMIT_SIDE_LEN,
    DETECTOR_DEFAULT_LIMIT_TYPE,
    DETECTOR_DEFAULT_THRESH,
    DETECTOR_DEFAULT_UNCLIP_RATIO,
    DETECTOR_DUAL_MERGE_VERSION,
    MOBILE_DETECTION_MODEL_NAME,
    SERVER_DETECTION_MODEL_NAME,
)
from backend.app.datasets.phase5.detector_calibration import (
    DetectorCalibrationConfig,
    build_bounded_calibration_grid,
    count_pathological_boxes,
    is_pathological_box,
    known_seed_gate_passes,
    mobile_baseline_params,
    rank_passing_candidates,
    sensitivity_match,
    server_baseline_params,
)
from backend.app.extraction.visual.detect_first_types import DetectorRuntimeParams


def test_mobile_defaults_match_phase4() -> None:
    params = mobile_baseline_params()
    assert params.thresh == DETECTOR_DEFAULT_THRESH == 0.30
    assert params.box_thresh == DETECTOR_DEFAULT_BOX_THRESH == 0.60
    assert params.unclip_ratio == DETECTOR_DEFAULT_UNCLIP_RATIO == 1.50
    assert params.limit_side_len == DETECTOR_DEFAULT_LIMIT_SIDE_LEN == 1600
    assert params.limit_type == DETECTOR_DEFAULT_LIMIT_TYPE == "max"


def test_server_baseline_not_blind_mobile_copy_contract() -> None:
    # Same published family defaults, but constructed via server_baseline_params.
    assert server_baseline_params() == mobile_baseline_params()


def test_bounded_grid_size_and_deterministic_ids() -> None:
    a = build_bounded_calibration_grid()
    b = build_bounded_calibration_grid()
    assert 1 <= len(a) <= DETECTOR_CALIBRATION_MAX_CONFIGS
    assert len(a) == 12
    assert [c.config_id for c in a] == [c.config_id for c in b]
    assert a[0].label == "mobile_c0_intrinsic"
    assert a[0].apply_params is False
    assert a[0].detection_model_name == MOBILE_DETECTION_MODEL_NAME
    families = {c.family for c in a}
    assert families == {"mobile", "server", "merged"}
    assert any(c.detection_model_name == SERVER_DETECTION_MODEL_NAME for c in a)
    assert all(c.merge_version == DETECTOR_DUAL_MERGE_VERSION for c in a if c.family == "merged")


def test_unbounded_search_rejected() -> None:
    with pytest.raises(ValueError, match="unbounded"):
        build_bounded_calibration_grid(max_configs=DETECTOR_CALIBRATION_MAX_CONFIGS + 1)


def test_invalid_threshold_rejection() -> None:
    with pytest.raises(ValueError, match="thresh"):
        DetectorRuntimeParams(thresh=0.0).validate()
    with pytest.raises(ValueError, match="box_thresh"):
        DetectorRuntimeParams(box_thresh=1.5).validate()
    with pytest.raises(ValueError, match="unclip"):
        DetectorRuntimeParams(unclip_ratio=0.5).validate()
    with pytest.raises(ValueError, match="limit_side_len"):
        DetectorRuntimeParams(limit_side_len=10).validate()
    with pytest.raises(ValueError, match="merged"):
        DetectorCalibrationConfig(
            family="merged",
            detection_model_name=MOBILE_DETECTION_MODEL_NAME,
            params=mobile_baseline_params(),
            merge_version=DETECTOR_DUAL_MERGE_VERSION,
        )


def test_pathological_full_page_box_rejected() -> None:
    full = NormalisedBoundingBox(x=0.0, y=0.0, width=0.99, height=0.99)
    small = NormalisedBoundingBox(x=0.1, y=0.1, width=0.2, height=0.05)
    assert is_pathological_box(full) is True
    assert is_pathological_box(small) is False
    assert count_pathological_boxes([full, small]) == 1


def test_sensitivity_modes() -> None:
    assert sensitivity_match("exact", mode="strict")
    assert not sensitivity_match("contained", mode="strict")
    assert sensitivity_match("contained", mode="containment_friendly")
    assert not sensitivity_match("fragmented", mode="containment_friendly")
    assert sensitivity_match("fragmented", mode="fragment_union")
    assert not sensitivity_match("missed", mode="fragment_union")


def test_known_seed_gate_and_ranking() -> None:
    passing_cov = {
        "handwriting_seed_total": 55,
        "missed_detections": 0,
        "by_category": {
            "digits": {"counts": {"contained": 10}, "recall": 1.0},
            "hand_printed": {"counts": {"contained": 5}, "recall": 1.0},
            "cursive": {"counts": {"contained": 11}, "recall": 1.0},
            "signature": {"counts": {"contained": 11}, "recall": 1.0},
            "longer_note": {"counts": {"contained": 5}, "recall": 1.0},
        },
    }
    assert known_seed_gate_passes(passing_cov)
    failing = dict(passing_cov)
    failing["missed_detections"] = 1
    assert not known_seed_gate_passes(failing)

    ranked = rank_passing_candidates(
        [
            {
                "config_id": "b",
                "gate_passed": True,
                "total_regions": 200,
                "detector_time_seconds": 1.0,
                "recognition_degradation_score": 0.0,
                "family": "merged",
            },
            {
                "config_id": "a",
                "gate_passed": True,
                "total_regions": 100,
                "detector_time_seconds": 2.0,
                "recognition_degradation_score": 0.0,
                "family": "mobile",
            },
            {"config_id": "c", "gate_passed": False, "total_regions": 10, "family": "mobile"},
        ]
    )
    assert [r["config_id"] for r in ranked] == ["a", "b"]


def test_server_model_name_official() -> None:
    assert SERVER_DETECTION_MODEL_NAME == "PP-OCRv5_server_det"

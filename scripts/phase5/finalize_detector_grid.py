#!/usr/bin/env python3
"""Finalize Task C1 grid from partial results + best merged pairs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase5.calibrate_detector_recall import (  # noqa: E402
    _emit,
    _load_seeds,
    _ocr_config,
    _reports_dir,
    _run_config_on_pages,
    _seed_pages,
    _write_report,
)


def main() -> int:
    from backend.app.datasets.phase5.constants import (
        DETECTOR_DUAL_MERGE_VERSION,
        MOBILE_DETECTION_MODEL_NAME,
        SERVER_DETECTION_MODEL_NAME,
    )
    from backend.app.datasets.phase5.detector_calibration import DetectorCalibrationConfig
    from backend.app.datasets.phase5.paths import default_private_root
    from backend.app.extraction.visual.detect_first_types import DetectorRuntimeParams

    private_root = default_private_root()
    partial_path = _reports_dir(private_root) / "grid-seed-comparison.partial.json"
    partial = json.loads(partial_path.read_text(encoding="utf-8"))
    results = list(partial.get("candidates") or [])
    done_labels = {r["label"] for r in results}

    settings, config = _ocr_config()
    seeds = _load_seeds(private_root)
    sources = _seed_pages(private_root, seeds)
    adapter_cache: dict = {}
    detection_cache: dict = {}

    extras = [
        DetectorCalibrationConfig(
            family="merged",
            detection_model_name=MOBILE_DETECTION_MODEL_NAME,
            params=DetectorRuntimeParams(),
            merge_partner_model_name=SERVER_DETECTION_MODEL_NAME,
            merge_partner_params=DetectorRuntimeParams(),
            merge_version=DETECTOR_DUAL_MERGE_VERSION,
            label="merged_intrinsics",
            apply_params=False,
        ),
        DetectorCalibrationConfig(
            family="merged",
            detection_model_name=MOBILE_DETECTION_MODEL_NAME,
            params=DetectorRuntimeParams(thresh=0.25, box_thresh=0.45, unclip_ratio=1.80),
            merge_partner_model_name=SERVER_DETECTION_MODEL_NAME,
            merge_partner_params=DetectorRuntimeParams(),
            merge_version=DETECTOR_DUAL_MERGE_VERSION,
            label="merged_mobile_recall_bias_plus_server_defaults",
            apply_params=True,
        ),
    ]

    skipped = [
        {
            "label": "server_recall_1920",
            "family": "server",
            "skipped": True,
            "skip_reason": "runtime_budget_exceeded_on_prior_server_settings_defaults",
            "gate_passed": False,
        },
        {
            "label": "server_faint_2400",
            "family": "server",
            "skipped": True,
            "skip_reason": "runtime_budget_exceeded_on_prior_server_settings_defaults",
            "gate_passed": False,
        },
        {
            "label": "merged_faint_2400",
            "family": "merged",
            "skipped": True,
            "skip_reason": "depends_on_skipped_server_faint_2400",
            "gate_passed": False,
        },
    ]

    for row in extras:
        if row.label in done_labels:
            continue
        print(f"[finalize] {row.label}", flush=True)
        result = _run_config_on_pages(
            config_row=row,
            sources=sources,
            private_root=private_root,
            runtime_config=config,
            adapter_cache=adapter_cache,
            detection_cache=detection_cache,
            with_rec=False,
        )
        results.append(result)
        print(
            f"[finalize] done recall={result.get('overall_recall')} "
            f"misses={result.get('misses')} sig={result.get('signature_recall')}",
            flush=True,
        )

    results.extend(skipped)
    payload = {
        "task": "grid",
        "calibration_version": "phase5-detector-calibration-v1",
        "config_count": len(results),
        "server_included": True,
        "shadow_enabled": settings.phase5_detect_first_shadow_enabled,
        "router_enabled": settings.handwriting_router_enabled,
        "note": (
            "server_recall_1920 / server_faint_2400 / merged_faint_2400 skipped after "
            "server_settings_defaults alone required ~416s on seed pages; remaining "
            "budget spent on merged pairs of the best completed single detectors."
        ),
        "candidates": results,
    }
    _write_report(private_root, "grid-seed-comparison.json", payload)
    _emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

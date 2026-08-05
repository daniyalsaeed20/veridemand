"""Bounded handwriting-detector calibration contracts (Phase 5 Task C1).

Offline/shadow only. No unbounded parameter search. Never imports Paddle.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Literal, cast

from backend.app.contracts.geometry import NormalisedBoundingBox
from backend.app.datasets.phase5.constants import (
    DETECTOR_CALIBRATION_MAX_CONFIGS,
    DETECTOR_CALIBRATION_VERSION,
    DETECTOR_DEFAULT_BOX_THRESH,
    DETECTOR_DEFAULT_LIMIT_SIDE_LEN,
    DETECTOR_DEFAULT_THRESH,
    DETECTOR_DEFAULT_UNCLIP_RATIO,
    DETECTOR_DUAL_MERGE_VERSION,
    DETECTOR_FIRST_SEED_CONTAIN_IOU,
    DETECTOR_FIRST_SEED_EXACT_IOU,
    DETECTOR_FIRST_SEED_FRAGMENT_IOU,
    DETECTOR_PATHOLOGICAL_BOX_AREA,
    MOBILE_DETECTION_MODEL_NAME,
    SERVER_DETECTION_MODEL_NAME,
)
from backend.app.datasets.phase5.detector_first import classify_seed_coverage
from backend.app.datasets.phase5.detector_first_schemas import SeedCoverageKind
from backend.app.datasets.phase5.schemas import HandwritingSeedRecord
from backend.app.extraction.visual.detect_first_types import DetectorRuntimeParams

DetectorFamily = Literal["mobile", "server", "merged"]
SensitivityMatchMode = Literal["strict", "containment_friendly", "fragment_union"]
RecognitionCompatibility = Literal[
    "acceptable_for_retraining",
    "requires_crop_or_merge_correction",
    "not_acceptable",
    "not_evaluated",
]


@dataclass(frozen=True, slots=True)
class DetectorCalibrationConfig:
    """One bounded, versioned detector candidate configuration."""

    family: DetectorFamily
    detection_model_name: str
    params: DetectorRuntimeParams
    merge_partner_model_name: str | None = None
    merge_partner_params: DetectorRuntimeParams | None = None
    merge_version: str | None = None
    label: str = ""
    # When False, detect_text is called without predict kwargs (C0 / model YAML defaults).
    apply_params: bool = True

    def __post_init__(self) -> None:
        self.params.validate()
        if self.merge_partner_params is not None:
            self.merge_partner_params.validate()
        if self.family == "merged":
            if not self.merge_partner_model_name or self.merge_partner_params is None:
                raise ValueError("merged configs require partner model and params")
            if self.merge_version != DETECTOR_DUAL_MERGE_VERSION:
                raise ValueError(f"merged configs must use {DETECTOR_DUAL_MERGE_VERSION}")
        elif self.merge_partner_model_name or self.merge_partner_params:
            raise ValueError("non-merged configs must not set merge partner fields")

    @property
    def config_id(self) -> str:
        payload = {
            "calibration_version": DETECTOR_CALIBRATION_VERSION,
            "family": self.family,
            "detection_model_name": self.detection_model_name,
            "params": asdict(self.params),
            "apply_params": self.apply_params,
            "merge_partner_model_name": self.merge_partner_model_name,
            "merge_partner_params": (
                asdict(self.merge_partner_params) if self.merge_partner_params is not None else None
            ),
            "merge_version": self.merge_version,
            "label": self.label,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return f"detcfg_{digest[:16]}"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "config_id": self.config_id,
            "calibration_version": DETECTOR_CALIBRATION_VERSION,
            "family": self.family,
            "detection_model_name": self.detection_model_name,
            "params": asdict(self.params),
            "apply_params": self.apply_params,
            "merge_partner_model_name": self.merge_partner_model_name,
            "merge_partner_params": (
                asdict(self.merge_partner_params) if self.merge_partner_params is not None else None
            ),
            "merge_version": self.merge_version,
            "label": self.label,
        }

    def predict_params(self) -> DetectorRuntimeParams | None:
        return self.params if self.apply_params else None

    def predict_partner_params(self) -> DetectorRuntimeParams | None:
        if not self.apply_params:
            return None
        return self.merge_partner_params


def mobile_baseline_params() -> DetectorRuntimeParams:
    """Reproduce Phase 4 / Task C0 mobile detector defaults."""

    return DetectorRuntimeParams(
        thresh=DETECTOR_DEFAULT_THRESH,
        box_thresh=DETECTOR_DEFAULT_BOX_THRESH,
        unclip_ratio=DETECTOR_DEFAULT_UNCLIP_RATIO,
        limit_side_len=DETECTOR_DEFAULT_LIMIT_SIDE_LEN,
        limit_type="max",
    )


def server_baseline_params() -> DetectorRuntimeParams:
    """Server detector baseline — same-family defaults, not a mobile copy."""

    return DetectorRuntimeParams(
        thresh=DETECTOR_DEFAULT_THRESH,
        box_thresh=DETECTOR_DEFAULT_BOX_THRESH,
        unclip_ratio=DETECTOR_DEFAULT_UNCLIP_RATIO,
        limit_side_len=DETECTOR_DEFAULT_LIMIT_SIDE_LEN,
        limit_type="max",
    )


def build_bounded_calibration_grid(
    *,
    include_server: bool = True,
    include_merged: bool = True,
    max_configs: int = DETECTOR_CALIBRATION_MAX_CONFIGS,
) -> list[DetectorCalibrationConfig]:
    """Return ≤ ``max_configs`` materially different calibration candidates."""

    if max_configs < 1:
        raise ValueError("max_configs must be >= 1")
    if max_configs > DETECTOR_CALIBRATION_MAX_CONFIGS:
        raise ValueError(
            f"unbounded search rejected: max_configs={max_configs} exceeds "
            f"{DETECTOR_CALIBRATION_MAX_CONFIGS}"
        )

    mobile = MOBILE_DETECTION_MODEL_NAME
    server = SERVER_DETECTION_MODEL_NAME
    configs: list[DetectorCalibrationConfig] = [
        DetectorCalibrationConfig(
            family="mobile",
            detection_model_name=mobile,
            params=mobile_baseline_params(),
            label="mobile_c0_intrinsic",
            apply_params=False,
        ),
        DetectorCalibrationConfig(
            family="mobile",
            detection_model_name=mobile,
            params=mobile_baseline_params(),
            label="mobile_settings_defaults",
            apply_params=True,
        ),
        DetectorCalibrationConfig(
            family="mobile",
            detection_model_name=mobile,
            params=DetectorRuntimeParams(thresh=0.20, box_thresh=0.50),
            label="mobile_soft_thresh",
        ),
        DetectorCalibrationConfig(
            family="mobile",
            detection_model_name=mobile,
            params=DetectorRuntimeParams(thresh=0.25, box_thresh=0.45, unclip_ratio=1.80),
            label="mobile_recall_bias",
        ),
        DetectorCalibrationConfig(
            family="mobile",
            detection_model_name=mobile,
            params=DetectorRuntimeParams(unclip_ratio=2.00, limit_side_len=1920),
            label="mobile_unclip_1920",
        ),
        DetectorCalibrationConfig(
            family="mobile",
            detection_model_name=mobile,
            params=DetectorRuntimeParams(
                thresh=0.20, box_thresh=0.40, unclip_ratio=1.80, limit_side_len=2400
            ),
            label="mobile_faint_2400",
        ),
    ]

    if include_server:
        configs.extend(
            [
                DetectorCalibrationConfig(
                    family="server",
                    detection_model_name=server,
                    params=server_baseline_params(),
                    label="server_intrinsic",
                    apply_params=False,
                ),
                DetectorCalibrationConfig(
                    family="server",
                    detection_model_name=server,
                    params=server_baseline_params(),
                    label="server_settings_defaults",
                ),
                DetectorCalibrationConfig(
                    family="server",
                    detection_model_name=server,
                    params=DetectorRuntimeParams(
                        thresh=0.25,
                        box_thresh=0.45,
                        unclip_ratio=1.80,
                        limit_side_len=1920,
                    ),
                    label="server_recall_1920",
                ),
                DetectorCalibrationConfig(
                    family="server",
                    detection_model_name=server,
                    params=DetectorRuntimeParams(
                        thresh=0.20,
                        box_thresh=0.40,
                        unclip_ratio=2.00,
                        limit_side_len=2400,
                    ),
                    label="server_faint_2400",
                ),
            ]
        )

    if include_merged and include_server:
        configs.extend(
            [
                DetectorCalibrationConfig(
                    family="merged",
                    detection_model_name=mobile,
                    params=mobile_baseline_params(),
                    merge_partner_model_name=server,
                    merge_partner_params=server_baseline_params(),
                    merge_version=DETECTOR_DUAL_MERGE_VERSION,
                    label="merged_intrinsics",
                    apply_params=False,
                ),
                DetectorCalibrationConfig(
                    family="merged",
                    detection_model_name=mobile,
                    params=DetectorRuntimeParams(
                        thresh=0.20,
                        box_thresh=0.40,
                        unclip_ratio=1.80,
                        limit_side_len=2400,
                    ),
                    merge_partner_model_name=server,
                    merge_partner_params=DetectorRuntimeParams(
                        thresh=0.20,
                        box_thresh=0.40,
                        unclip_ratio=2.00,
                        limit_side_len=2400,
                    ),
                    merge_version=DETECTOR_DUAL_MERGE_VERSION,
                    label="merged_faint_2400",
                ),
            ]
        )

    if len(configs) > max_configs:
        configs = configs[:max_configs]
    seen: set[str] = set()
    unique: list[DetectorCalibrationConfig] = []
    for cfg in configs:
        if cfg.config_id in seen:
            continue
        seen.add(cfg.config_id)
        unique.append(cfg)
    return unique


def is_pathological_box(
    bbox: NormalisedBoundingBox,
    *,
    area_limit: float = DETECTOR_PATHOLOGICAL_BOX_AREA,
) -> bool:
    """True when a normalised box covers nearly the entire page."""

    area = float(bbox.width * bbox.height)
    near_full = bbox.width >= 0.95 and bbox.height >= 0.95
    return area >= area_limit or near_full


def count_pathological_boxes(
    bboxes: list[NormalisedBoundingBox],
    *,
    area_limit: float = DETECTOR_PATHOLOGICAL_BOX_AREA,
) -> int:
    return sum(1 for b in bboxes if is_pathological_box(b, area_limit=area_limit))


def sensitivity_match(
    kind: SeedCoverageKind,
    *,
    mode: SensitivityMatchMode,
) -> bool:
    """Whether a seed coverage kind counts as detected under ``mode``."""

    if mode == "strict":
        return kind in {"exact", "near_exact"}
    if mode == "containment_friendly":
        return kind in {"exact", "near_exact", "contained"}
    if mode == "fragment_union":
        return kind in {"exact", "near_exact", "contained", "fragmented"}
    raise ValueError(f"unknown sensitivity mode: {mode}")


def summarise_seed_coverage_sensitivity(
    seeds: list[HandwritingSeedRecord],
    page_detector_bboxes: dict[str, list[NormalisedBoundingBox]],
    *,
    exact_iou: float = DETECTOR_FIRST_SEED_EXACT_IOU,
    contain_iou: float = DETECTOR_FIRST_SEED_CONTAIN_IOU,
    fragment_iou: float = DETECTOR_FIRST_SEED_FRAGMENT_IOU,
) -> dict[str, Any]:
    """Report strict / containment-friendly / fragment-union recalls (no IDs)."""

    active = [s for s in seeds if s.status == "active"]
    modes: dict[str, dict[str, Any]] = {}
    mode_list: tuple[SensitivityMatchMode, ...] = (
        "strict",
        "containment_friendly",
        "fragment_union",
    )
    for mode in mode_list:
        detected = 0
        kinds: Counter[str] = Counter()
        by_category: dict[str, Counter[str]] = {}
        for seed in active:
            boxes = page_detector_bboxes.get(seed.opaque_page_reference, [])
            kind = classify_seed_coverage(
                seed.geometry_normalized,
                boxes,
                exact_iou=exact_iou,
                contain_iou=contain_iou,
                fragment_iou=fragment_iou,
            )
            kinds[kind] += 1
            if sensitivity_match(kind, mode=mode):
                detected += 1
            for cat in seed.categories:
                by_category.setdefault(cat, Counter())[kind] += 1

        def _mode_recall(counter: Counter[str], *, match_mode: SensitivityMatchMode) -> float:
            total = sum(counter.values())
            if total == 0:
                return 0.0
            hit = 0
            for k, n in counter.items():
                if sensitivity_match(cast(SeedCoverageKind, k), mode=match_mode):
                    hit += n
            return float(hit / total)

        modes[mode] = {
            "detected_count": detected,
            "recall": (detected / len(active)) if active else 0.0,
            "coverage_kinds": dict(kinds),
            "by_category_recall": {
                cat: _mode_recall(ctr, match_mode=mode) for cat, ctr in sorted(by_category.items())
            },
        }
    return {
        "handwriting_seed_total": len(active),
        "sensitivity": modes,
        "geometry_criteria": {
            "exact_iou": exact_iou,
            "contain_iou": contain_iou,
            "fragment_iou": fragment_iou,
            "primary_gate": "c0_detected_includes_fragmented",
        },
    }


def known_seed_gate_passes(seed_coverage: dict[str, Any]) -> bool:
    """Prototype gate: zero misses on overall + required style slices."""

    total = int(seed_coverage.get("handwriting_seed_total", 0))
    missed = int(seed_coverage.get("missed_detections", 0))
    if total <= 0 or missed != 0:
        return False
    by_cat = seed_coverage.get("by_category") or {}
    required = ("digits", "hand_printed", "cursive", "signature", "longer_note")
    for cat in required:
        info = by_cat.get(cat) or {}
        counts = info.get("counts") or {}
        if int(counts.get("missed", 0)) != 0:
            return False
    return True


def rank_passing_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rank gate-passing candidates: fewest regions, then time, then simplicity."""

    def _key(row: dict[str, Any]) -> tuple[Any, ...]:
        family = str(row.get("family", "merged"))
        simplicity = {"mobile": 0, "server": 1, "merged": 2}.get(family, 9)
        return (
            int(row.get("total_regions", 10**9)),
            float(row.get("detector_time_seconds", 10**9)),
            float(row.get("recognition_degradation_score", 10**9)),
            simplicity,
            str(row.get("config_id", "")),
        )

    passing = [c for c in candidates if c.get("gate_passed")]
    return sorted(passing, key=_key)

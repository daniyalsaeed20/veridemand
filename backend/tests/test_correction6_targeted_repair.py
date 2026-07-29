"""Correction 6 — targeted regional OCR repair unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from backend.app.contracts.geometry import (
    Geometry,
    NormalisedBoundingBox,
    NormalisedPoint,
    NormalisedPolygon,
)
from backend.app.contracts.native import NativeWord
from backend.app.contracts.repair import (
    REPAIR_POLICY_VERSION,
    RepairMethod,
    RepairQualityStatus,
)
from backend.app.extraction.routing.models import RoutingPolicy
from backend.app.extraction.routing.repair_clustering import cluster_failed_boxes
from backend.app.extraction.routing.repair_coordinates import (
    build_crop_transform,
    map_repaired_crop_polygon,
    normalised_bbox_to_pixel_crop,
)
from backend.app.extraction.routing.repair_eligibility import evaluate_targeted_repair_eligibility
from backend.app.extraction.routing.repair_quality import evaluate_repair_quality
from backend.app.extraction.routing.repair_reconcile import (
    RepairedWordCandidate,
    classify_base_words,
    reconcile_repaired_page,
)
from backend.app.settings.config import Settings


def _policy(**overrides: object) -> RoutingPolicy:
    base = RoutingPolicy.from_settings(Settings())
    if not overrides:
        return base
    from dataclasses import replace

    return replace(base, **overrides)  # type: ignore[arg-type]


def _word(
    i: int, x: float, y: float, text: str = "word", *, w: float = 0.08, h: float = 0.03
) -> NativeWord:
    from backend.app.contracts.native import (
        PdfPointBox,
        RecognitionMethod,
        RecognitionStatus,
        SourceMode,
    )

    bbox = NormalisedBoundingBox(x=x, y=y, width=w, height=h)
    poly = NormalisedPolygon(
        points=[
            NormalisedPoint(x=bbox.x, y=bbox.y),
            NormalisedPoint(x=bbox.x + bbox.width, y=bbox.y),
            NormalisedPoint(x=bbox.x + bbox.width, y=bbox.y + bbox.height),
            NormalisedPoint(x=bbox.x, y=bbox.y + bbox.height),
        ]
    )
    return NativeWord(
        id=f"nw_{i:04d}",
        page_number=1,
        sequence_index=i,
        text=text,
        normalised_text=text,
        character_ids=[],
        geometry=Geometry(polygon=poly, bbox=bbox),
        pdf_point_bbox=PdfPointBox(x=x * 612, y=y * 792, width=w * 612, height=h * 792),
        upright=True,
        recognition_method=RecognitionMethod.NATIVE_PDF,
        source_mode=SourceMode.NATIVE_AUTHORITY,
        recognition_status=RecognitionStatus.ACCEPTED,
    )


def test_bounded_failures_are_repair_eligible() -> None:
    words = [_word(i, 0.1 + (i % 5) * 0.12, 0.2 + (i // 5) * 0.08, f"w{i}") for i in range(20)]
    failed = [2]
    policy = _policy()
    regions = cluster_failed_boxes(words, failed, page_number=1, policy=policy)
    evidence = evaluate_targeted_repair_eligibility(
        page_number=1,
        words=words,
        failed_indices=failed,
        regions=regions,
        policy=policy,
        visual_agreement_score=0.82,
        recognition_agreement_score=0.80,
    )
    assert evidence.repair_eligible is True
    assert evidence.full_ocr_fallback_required is False
    assert evidence.repair_method is RepairMethod.RECOGNITION_ONLY
    assert evidence.policy_version == REPAIR_POLICY_VERSION or evidence.policy_version.startswith(
        "phase4-targeted-repair"
    )


def test_widespread_failures_not_eligible() -> None:
    words = [_word(i, 0.05 + (i % 4) * 0.2, 0.1 + (i // 4) * 0.12, f"w{i}") for i in range(16)]
    failed = list(range(12))
    policy = _policy()
    regions = cluster_failed_boxes(words, failed, page_number=1, policy=policy)
    evidence = evaluate_targeted_repair_eligibility(
        page_number=1,
        words=words,
        failed_indices=failed,
        regions=regions,
        policy=policy,
        visual_agreement_score=0.40,
        recognition_agreement_score=0.40,
    )
    assert evidence.repair_eligible is False
    assert evidence.full_ocr_fallback_required is True


def test_region_clustering_deterministic_and_nearby() -> None:
    words = [
        _word(0, 0.10, 0.20, "a"),
        _word(1, 0.20, 0.20, "b"),
        _word(2, 0.70, 0.80, "c"),
    ]
    policy = _policy()
    r1 = cluster_failed_boxes(words, [0, 1, 2], page_number=1, policy=policy)
    r2 = cluster_failed_boxes(words, [0, 1, 2], page_number=1, policy=policy)
    assert [x.repair_region_id for x in r1] == [x.repair_region_id for x in r2]
    # Nearby on same line cluster; distant remains separate.
    assert len(r1) == 2
    assert len(r1[0].source_word_ids) == 2
    assert len(r1[1].source_word_ids) == 1


def test_distant_boxes_remain_separate() -> None:
    words = [_word(0, 0.1, 0.1, "a"), _word(1, 0.8, 0.85, "b")]
    regions = cluster_failed_boxes(words, [0, 1], page_number=1, policy=_policy())
    assert len(regions) == 2


def test_padding_stays_in_page_bounds() -> None:
    words = [_word(0, 0.0, 0.0, "edge", w=0.05, h=0.04)]
    regions = cluster_failed_boxes(words, [0], page_number=1, policy=_policy())
    assert len(regions) == 1
    box = regions[0].expanded_normalised_bbox
    assert 0.0 <= box.x <= 1.0
    assert 0.0 <= box.y <= 1.0
    assert box.x + box.width <= 1.0 + 1e-9
    assert box.y + box.height <= 1.0 + 1e-9


def test_method_selection_recognition_vs_local() -> None:
    words = [_word(i, 0.05 + i * 0.08, 0.2, f"w{i}") for i in range(10)]
    failed = [1]
    regions = cluster_failed_boxes(words, failed, page_number=1, policy=_policy())
    rec = evaluate_targeted_repair_eligibility(
        page_number=1,
        words=words,
        failed_indices=failed,
        regions=regions,
        policy=_policy(),
        visual_agreement_score=0.8,
        recognition_agreement_score=0.5,
        geometry_shifted=False,
    )
    local = evaluate_targeted_repair_eligibility(
        page_number=1,
        words=words,
        failed_indices=failed,
        regions=regions,
        policy=_policy(),
        visual_agreement_score=0.8,
        recognition_agreement_score=0.5,
        geometry_shifted=True,
    )
    assert rec.repair_method is RepairMethod.RECOGNITION_ONLY
    assert local.repair_method is RepairMethod.LOCAL_DETECTION_AND_RECOGNITION


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_coordinate_round_trip_rotations(rotation: int) -> None:
    bbox = NormalisedBoundingBox(x=0.2, y=0.3, width=0.2, height=0.1)
    transform = build_crop_transform(
        bbox,
        page_width_px=1000,
        page_height_px=1400,
        page_width_points=612.0,
        page_height_points=792.0,
        render_scale=1000 / 612.0,
        intrinsic_rotation=rotation,
    )
    assert transform.intrinsic_rotation == rotation
    local = [(10.0, 5.0), (80.0, 5.0), (80.0, 40.0), (10.0, 40.0)]
    polygon, out_bbox, geometry, _, _ = map_repaired_crop_polygon(local, transform)
    assert geometry.bbox.width > 0
    assert out_bbox.x >= 0.0 and out_bbox.y >= 0.0
    assert out_bbox.x + out_bbox.width <= 1.0 + 1e-6
    assert out_bbox.y + out_bbox.height <= 1.0 + 1e-6
    assert len(polygon.points) >= 3


def test_non_zero_box_origins_and_small_pages() -> None:
    bbox = NormalisedBoundingBox(x=0.05, y=0.05, width=0.4, height=0.3)
    x0, y0, x1, y1 = normalised_bbox_to_pixel_crop(bbox, page_width_px=200, page_height_px=200)
    assert x0 >= 0 and y0 >= 0
    assert x1 > x0 and y1 > y0


def test_unaffected_words_retained_and_failed_suppressed() -> None:
    words = [_word(i, 0.1 + i * 0.15, 0.2, f"w{i}") for i in range(5)]
    failed = [2]
    regions = cluster_failed_boxes(words, failed, page_number=1, policy=_policy())
    classified = classify_base_words(words, failed_indices=failed, regions=regions)
    retained = [c for c in classified if c.retention.value in {"retained", "unaffected"}]
    suppressed = [c for c in classified if c.retention.value == "suppressed_for_repair"]
    assert len(suppressed) == 1
    assert len(retained) >= 3


def test_reconcile_prevents_duplicates_and_stable_ids() -> None:
    words = [_word(i, 0.1 + i * 0.15, 0.25, f"w{i}") for i in range(4)]
    failed = [1]
    regions = cluster_failed_boxes(words, failed, page_number=1, policy=_policy())
    classified = classify_base_words(words, failed_indices=failed, regions=regions)
    poly = regions[0].expanded_normalised_bbox
    from backend.app.contracts.geometry import Geometry, NormalisedPoint, NormalisedPolygon
    from backend.app.contracts.ocr import PixelBoundingBox, PixelPolygon

    repaired_poly = NormalisedPolygon(
        points=[
            NormalisedPoint(x=poly.x, y=poly.y),
            NormalisedPoint(x=poly.x + poly.width, y=poly.y),
            NormalisedPoint(x=poly.x + poly.width, y=poly.y + poly.height),
            NormalisedPoint(x=poly.x, y=poly.y + poly.height),
        ]
    )
    cand = RepairedWordCandidate(
        text="fixed",
        recognition_score=0.9,
        polygon=repaired_poly,
        bbox=poly,
        geometry=Geometry(polygon=repaired_poly, bbox=poly),
        pixel_polygon=PixelPolygon(points=[(0, 0), (10, 0), (10, 10), (0, 10)]),
        pixel_bbox=PixelBoundingBox(x=0, y=0, width=10, height=10),
        method=RepairMethod.RECOGNITION_ONLY,
        repair_region_id=regions[0].repair_region_id,
    )
    result = reconcile_repaired_page(
        page_number=1,
        classified=classified,
        repaired=[cand, cand],
        regions=regions,
        width_px=1000,
        height_px=1400,
    )
    assert result.summary.repaired_words == 1
    assert result.summary.suppressed_words >= 1
    ids = [w.id for w in result.words]
    assert len(ids) == len(set(ids))
    assert all(w.id.startswith("ocrword_p0001_") for w in result.words)


def test_quality_gate_pass_and_fail_to_full_ocr() -> None:
    words = [_word(0, 0.2, 0.2, "a")]
    regions = cluster_failed_boxes(words, [0], page_number=1, policy=_policy())
    from backend.app.contracts.geometry import Geometry, NormalisedPoint, NormalisedPolygon
    from backend.app.contracts.ocr import PixelBoundingBox, PixelPolygon

    poly = regions[0].expanded_normalised_bbox
    repaired_poly = NormalisedPolygon(
        points=[
            NormalisedPoint(x=poly.x, y=poly.y),
            NormalisedPoint(x=poly.x + poly.width, y=poly.y),
            NormalisedPoint(x=poly.x + poly.width, y=poly.y + poly.height),
            NormalisedPoint(x=poly.x, y=poly.y + poly.height),
        ]
    )
    good = RepairedWordCandidate(
        text="ok",
        recognition_score=0.92,
        polygon=repaired_poly,
        bbox=poly,
        geometry=Geometry(polygon=repaired_poly, bbox=poly),
        pixel_polygon=PixelPolygon(points=[(0, 0), (10, 0), (10, 10), (0, 10)]),
        pixel_bbox=PixelBoundingBox(x=0, y=0, width=10, height=10),
        method=RepairMethod.RECOGNITION_ONLY,
        repair_region_id=regions[0].repair_region_id,
    )
    passed = evaluate_repair_quality(
        page_number=1,
        regions=regions,
        repaired=[good],
        policy=_policy(),
        expected_failed_word_count=1,
    )
    assert passed.status in {
        RepairQualityStatus.REPAIR_COMPLETE,
        RepairQualityStatus.REPAIR_COMPLETE_WITH_WARNINGS,
    }
    assert passed.fallback_to_full_ocr is False

    failed = evaluate_repair_quality(
        page_number=1,
        regions=regions,
        repaired=[],
        policy=_policy(),
        expected_failed_word_count=1,
    )
    assert failed.status is RepairQualityStatus.REPAIR_INSUFFICIENT
    assert failed.fallback_to_full_ocr is True


@pytest.mark.asyncio
async def test_pipeline_atomic_publish_and_cleanup(tmp_path: Path) -> None:
    from backend.app.extraction.routing.repair_pipeline import (
        cleanup_repair_staging,
        repair_staging_dir,
        run_targeted_repair_pipeline,
    )

    words = [_word(i, 0.05 + i * 0.1, 0.25, f"word{i}") for i in range(8)]
    failed = [3]
    image = Image.new("RGB", (800, 1000), (255, 255, 255))
    results = tmp_path / "results"
    staging = tmp_path / "staging"
    results.mkdir()
    staging.mkdir()

    def recognise(img: Image.Image) -> tuple[str, float]:
        return "fixed", 0.95

    def detect_rec(
        img: Image.Image, limit: int | None
    ) -> list[tuple[str, float, list[tuple[float, float]]]]:
        return [("fixed", 0.95, [(5.0, 5.0), (40.0, 5.0), (40.0, 20.0), (5.0, 20.0)])]

    outcome = await run_targeted_repair_pipeline(
        page_number=1,
        words=words,
        failed_indices=failed,
        page_image=image,
        policy=_policy(),
        visual_agreement_score=0.85,
        recognition_agreement_score=0.6,
        page_width_points=612.0,
        page_height_points=792.0,
        render_scale=800 / 612.0,
        intrinsic_rotation=0,
        recognise_crop=recognise,
        detect_recognise=detect_rec,
        results_dir=results,
        staging_dir=staging,
        document_id="doc-test",
    )
    assert outcome.fallback_to_full_ocr is False
    assert outcome.page_result is not None
    assert outcome.page_result.page_result_state is not None
    assert outcome.page_result.page_result_state.value == "embedded_ocr_targeted_repair"
    assert outcome.page_result.source_label == "Verified embedded OCR with visual repair"
    assert (results / "page-0001.json").exists()
    assert not repair_staging_dir(staging, 1).exists()
    # Residual cleanup is idempotent.
    cleanup_repair_staging(repair_staging_dir(staging, 1))


@pytest.mark.asyncio
async def test_pipeline_cancellation_cleans_staging(tmp_path: Path) -> None:
    from backend.app.extraction.routing.repair_pipeline import run_targeted_repair_pipeline
    from backend.app.processing.cancellation import CancellationToken, JobCancelledError

    words = [_word(i, 0.1 + i * 0.1, 0.2, f"w{i}") for i in range(6)]
    image = Image.new("RGB", (600, 800), (255, 255, 255))
    token = CancellationToken()
    token.cancel()
    with pytest.raises(JobCancelledError):
        await run_targeted_repair_pipeline(
            page_number=1,
            words=words,
            failed_indices=[1],
            page_image=image,
            policy=_policy(),
            visual_agreement_score=0.8,
            recognition_agreement_score=None,
            page_width_points=612.0,
            page_height_points=792.0,
            render_scale=1.0,
            intrinsic_rotation=0,
            recognise_crop=lambda img: ("x", 0.9),
            detect_recognise=lambda img, lim: [],
            results_dir=tmp_path / "r",
            staging_dir=tmp_path / "s",
            cancel_token=token,
        )
    assert not (tmp_path / "s" / "targeted_repair").exists()


def test_synthetic_fixtures_exist() -> None:
    root = (
        Path(__file__).resolve().parents[2] / "fixtures" / "synthetic" / "ocr" / "targeted-repair"
    )
    assert (root / "MANIFEST.json").is_file()
    for name in [
        "A-one-wrong-word.pdf",
        "F-large-defective-region.pdf",
        "H-clean-embedded.pdf",
        "I-image-only.pdf",
    ]:
        assert (root / name).is_file()

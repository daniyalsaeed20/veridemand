"""Phase 5 handwriting classifier unit tests (Task 2 foundation)."""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from backend.app.contracts.ocr import (
    HandwritingClassificationEvidence,
    HandwritingClassificationLifecycle,
    HandwritingClassificationOutcome,
    HandwritingDecisionReason,
    HandwritingInferenceSource,
)
from backend.app.extraction.handwriting_router.manifest import (
    HandwritingModelRecord,
)
from backend.app.extraction.handwriting_router.preprocess import preprocess_crop
from backend.app.extraction.handwriting_router.routing import (
    RoutingThresholds,
    decide_routing_outcome,
)
from backend.app.extraction.handwriting_router.service import HandwritingClassifierService
from backend.app.extraction.handwriting_router.verifier import (
    VerificationFailureCode,
    verify_classifier_package,
)
from backend.app.settings.config import Settings

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "handwriting_classifier"
THRESH = RoutingThresholds(printed=0.85, handwritten=0.70, non_text=0.80, minimum_class_margin=0.10)


def test_lifecycle_and_outcome_are_distinct_enums() -> None:
    assert HandwritingClassificationOutcome.UNCERTAIN.value == "uncertain"
    assert "uncertain" not in {m.value for m in HandwritingClassificationLifecycle}
    evidence = HandwritingClassificationEvidence(
        lifecycle=HandwritingClassificationLifecycle.UNAVAILABLE,
        outcome=HandwritingClassificationOutcome.UNCERTAIN,
        decision_reason=HandwritingDecisionReason.MODEL_UNAVAILABLE,
        inference_source=HandwritingInferenceSource.SAFETY_ABSTENTION,
    )
    assert evidence.lifecycle is HandwritingClassificationLifecycle.UNAVAILABLE
    assert evidence.outcome is HandwritingClassificationOutcome.UNCERTAIN


def test_settings_defaults_preserve_phase4() -> None:
    settings = Settings()
    assert settings.handwriting_router_enabled is False
    assert settings.handwriting_classifier_required is False
    assert settings.printed_threshold == 0.85
    assert settings.handwriting_threshold == 0.70
    assert settings.non_text_threshold == 0.80
    assert settings.minimum_class_margin == 0.10


def test_settings_reject_required_when_disabled() -> None:
    with pytest.raises(ValueError, match="HANDWRITING_CLASSIFIER_REQUIRED"):
        Settings(
            handwriting_router_enabled=False,
            handwriting_classifier_required=True,
        )


def test_settings_invalid_threshold() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(printed_threshold=1.5)


@pytest.mark.parametrize(
    ("scores", "expected_outcome", "expected_reason"),
    [
        (
            [0.90, 0.05, 0.05],
            HandwritingClassificationOutcome.PRINTED,
            HandwritingDecisionReason.PRINTED_THRESHOLD_MET,
        ),
        (
            [0.05, 0.85, 0.10],
            HandwritingClassificationOutcome.HANDWRITTEN,
            HandwritingDecisionReason.HANDWRITING_THRESHOLD_MET,
        ),
        (
            [0.05, 0.05, 0.90],
            HandwritingClassificationOutcome.NON_TEXT,
            HandwritingDecisionReason.NON_TEXT_THRESHOLD_MET,
        ),
        (
            [0.40, 0.35, 0.25],
            HandwritingClassificationOutcome.UNCERTAIN,
            HandwritingDecisionReason.LOW_TOP_PROBABILITY,
        ),
        (
            [0.90, 0.90, 0.00],
            HandwritingClassificationOutcome.UNCERTAIN,
            HandwritingDecisionReason.THRESHOLD_CONFLICT,
        ),
        (
            [0.90, 0.05, 0.86],
            HandwritingClassificationOutcome.UNCERTAIN,
            HandwritingDecisionReason.THRESHOLD_CONFLICT,
        ),
        (
            [0.88, 0.87, 0.01],
            HandwritingClassificationOutcome.UNCERTAIN,
            HandwritingDecisionReason.THRESHOLD_CONFLICT,
        ),
    ],
)
def test_routing_matrix(
    scores: list[float],
    expected_outcome: HandwritingClassificationOutcome,
    expected_reason: HandwritingDecisionReason,
) -> None:
    decision = decide_routing_outcome(scores, THRESH)
    assert decision.outcome is expected_outcome
    assert decision.decision_reason is expected_reason


def test_routing_low_class_margin() -> None:
    thr = RoutingThresholds(
        printed=0.50, handwritten=0.50, non_text=0.50, minimum_class_margin=0.15
    )
    decision = decide_routing_outcome([0.55, 0.45, 0.0], thr)
    assert decision.outcome is HandwritingClassificationOutcome.UNCERTAIN
    assert decision.decision_reason is HandwritingDecisionReason.LOW_CLASS_MARGIN


def test_routing_rejects_nan_and_inf() -> None:
    for bad in ([float("nan"), 0.1, 0.1], [float("inf"), 0.0, 0.0], [0.5, 0.5]):
        decision = decide_routing_outcome(bad, THRESH)
        assert decision.outcome is HandwritingClassificationOutcome.UNCERTAIN
        assert decision.decision_reason is HandwritingDecisionReason.INVALID_OUTPUT


def test_fixture_package_verifies_with_allow_flag() -> None:
    assert FIXTURE_DIR.is_dir()
    result = verify_classifier_package(FIXTURE_DIR, allow_test_fixture=True)
    assert result.ready is True
    assert result.checksum_ok is True
    assert result.runtime_provider == "CPUExecutionProvider"


def test_test_fixture_rejected_for_production() -> None:
    result = verify_classifier_package(FIXTURE_DIR, allow_test_fixture=False)
    assert result.ready is False
    assert result.failure_code is VerificationFailureCode.TEST_FIXTURE_NOT_ALLOWED


def test_checksum_mismatch_detected(tmp_path: Path) -> None:
    # Copy fixture and corrupt model bytes while keeping record hash.
    dest = tmp_path / "pkg"
    dest.mkdir()
    for name in ("model.onnx", "labels.json", "model-record.json", "metrics.json"):
        (dest / name).write_bytes((FIXTURE_DIR / name).read_bytes())
    model = dest / "model.onnx"
    model.write_bytes(model.read_bytes() + b"\x00")
    result = verify_classifier_package(dest, allow_test_fixture=True)
    assert result.ready is False
    assert result.failure_code is VerificationFailureCode.CHECKSUM_MISMATCH


def test_labels_reject_uncertain_class(tmp_path: Path) -> None:
    dest = tmp_path / "pkg"
    dest.mkdir()
    for name in ("model.onnx", "model-record.json", "metrics.json"):
        (dest / name).write_bytes((FIXTURE_DIR / name).read_bytes())
    (dest / "labels.json").write_text(
        json.dumps(["printed", "handwritten", "uncertain"]), encoding="utf-8"
    )
    result = verify_classifier_package(dest, allow_test_fixture=True)
    assert result.ready is False
    assert result.failure_code is VerificationFailureCode.LABELS_INVALID


def test_manifest_rejects_unknown_field() -> None:
    from pydantic import ValidationError

    raw = json.loads((FIXTURE_DIR / "model-record.json").read_text(encoding="utf-8"))
    raw["unexpected_field"] = True
    with pytest.raises(ValidationError):
        HandwritingModelRecord.model_validate(raw)


def test_preprocess_deterministic() -> None:
    record = HandwritingModelRecord.model_validate_json(
        (FIXTURE_DIR / "model-record.json").read_text(encoding="utf-8")
    )
    image = Image.new("RGB", (40, 20), color=(12, 34, 56))
    a = preprocess_crop(image, record)
    b = preprocess_crop(image, record)
    assert a.shape == (1, 3, record.target_height, record.target_width)
    assert np.allclose(a, b)
    assert np.all(np.isfinite(a))


def test_session_reuse() -> None:
    settings = Settings(
        handwriting_router_enabled=True,
        handwriting_classifier_required=False,
        handwriting_classifier_path=FIXTURE_DIR,
        printed_threshold=0.50,
        handwriting_threshold=0.50,
        non_text_threshold=0.50,
        minimum_class_margin=0.05,
        ocr_enabled=False,
    )
    service = HandwritingClassifierService(settings)
    image = Image.new("RGB", (32, 32), color=(255, 255, 255))
    r1 = service.classify_crop(image, allow_test_fixture=True)
    r2 = service.classify_crop(image, allow_test_fixture=True)
    assert service.session_create_count == 1
    assert r1.lifecycle is HandwritingClassificationLifecycle.CLASSIFIED
    assert r2.lifecycle is HandwritingClassificationLifecycle.CLASSIFIED
    assert r1.outcome is HandwritingClassificationOutcome.PRINTED


def test_concurrent_init_single_session() -> None:
    settings = Settings(
        handwriting_router_enabled=True,
        handwriting_classifier_path=FIXTURE_DIR,
        ocr_enabled=False,
    )
    service = HandwritingClassifierService(settings)
    image = Image.new("RGB", (32, 32), color=(200, 200, 200))
    errors: list[BaseException] = []

    def _run() -> None:
        try:
            service.classify_crop(image, allow_test_fixture=True)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_run) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert service.session_create_count == 1


def test_disabled_router_does_not_create_session() -> None:
    settings = Settings(
        handwriting_router_enabled=False,
        handwriting_classifier_path=FIXTURE_DIR,
    )
    service = HandwritingClassifierService(settings)
    result = service.classify_crop(Image.new("RGB", (8, 8), color=(0, 0, 0)))
    assert result.lifecycle is HandwritingClassificationLifecycle.NOT_RUN
    assert result.outcome is None
    assert service.session_create_count == 0


def test_missing_package_unavailable() -> None:
    settings = Settings(
        handwriting_router_enabled=True,
        handwriting_classifier_path=Path("./models/handwriting_classifier"),
    )
    service = HandwritingClassifierService(settings)
    result = service.classify_crop(Image.new("RGB", (16, 16), color=(1, 2, 3)), enforced=True)
    assert result.lifecycle is HandwritingClassificationLifecycle.UNAVAILABLE
    assert result.outcome is HandwritingClassificationOutcome.UNCERTAIN


def test_batch_classify() -> None:
    settings = Settings(
        handwriting_router_enabled=True,
        handwriting_classifier_path=FIXTURE_DIR,
        handwriting_classifier_batch_size=2,
        printed_threshold=0.50,
        handwriting_threshold=0.50,
        non_text_threshold=0.50,
        minimum_class_margin=0.05,
        ocr_enabled=False,
    )
    service = HandwritingClassifierService(settings)
    images = [Image.new("RGB", (24, 24), color=(255, 255, 255)) for _ in range(3)]
    results = service.classify_crops(images, region_ids=["a", "b", "c"], allow_test_fixture=True)
    assert len(results) == 3
    assert all(r.outcome is HandwritingClassificationOutcome.PRINTED for r in results)
    assert service.session_create_count == 1


def test_fixture_sha_documented() -> None:
    digest = hashlib.sha256((FIXTURE_DIR / "model.onnx").read_bytes()).hexdigest()
    record = json.loads((FIXTURE_DIR / "model-record.json").read_text(encoding="utf-8"))
    assert digest == record["model_sha256"]

"""Phase 5 handwriting classifier unit tests (Task B3 dual-risk foundation)."""

from __future__ import annotations

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
THRESH = RoutingThresholds(
    handwriting_accept_threshold=0.70,
    handwriting_safe_low_threshold=0.20,
    non_text_accept_threshold=0.70,
    non_text_safe_low_threshold=0.20,
)


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
    assert settings.handwriting_accept_threshold == 0.70
    assert settings.handwriting_safe_low_threshold == 0.20
    assert settings.non_text_accept_threshold == 0.70
    assert settings.non_text_safe_low_threshold == 0.20


def test_settings_reject_required_when_disabled() -> None:
    with pytest.raises(ValueError, match="HANDWRITING_CLASSIFIER_REQUIRED"):
        Settings(
            handwriting_router_enabled=False,
            handwriting_classifier_required=True,
        )


def test_settings_invalid_threshold_order() -> None:
    with pytest.raises(ValueError, match="safe_low"):
        Settings(
            handwriting_accept_threshold=0.20,
            handwriting_safe_low_threshold=0.70,
        )


def test_settings_invalid_threshold_range() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(handwriting_accept_threshold=1.5)


@pytest.mark.parametrize(
    ("scores", "expected_outcome", "expected_reason"),
    [
        (
            [0.05, 0.05],
            HandwritingClassificationOutcome.PRINTED,
            HandwritingDecisionReason.PRINTED_THRESHOLD_MET,
        ),
        (
            [0.90, 0.10],
            HandwritingClassificationOutcome.HANDWRITTEN,
            HandwritingDecisionReason.HANDWRITING_THRESHOLD_MET,
        ),
        (
            [0.05, 0.90],
            HandwritingClassificationOutcome.NON_TEXT,
            HandwritingDecisionReason.NON_TEXT_THRESHOLD_MET,
        ),
        (
            [0.40, 0.10],
            HandwritingClassificationOutcome.UNCERTAIN,
            HandwritingDecisionReason.LOW_TOP_PROBABILITY,
        ),
        (
            [0.90, 0.90],
            HandwritingClassificationOutcome.UNCERTAIN,
            HandwritingDecisionReason.THRESHOLD_CONFLICT,
        ),
        (
            [0.50, 0.50],
            HandwritingClassificationOutcome.UNCERTAIN,
            HandwritingDecisionReason.LOW_TOP_PROBABILITY,
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


def test_material_handwriting_never_non_text() -> None:
    decision = decide_routing_outcome([0.35, 0.95], THRESH)
    assert decision.outcome is HandwritingClassificationOutcome.UNCERTAIN
    assert decision.outcome.value != "non_text"


def test_printed_only_when_both_safely_low() -> None:
    decision = decide_routing_outcome([0.25, 0.05], THRESH)
    assert decision.outcome is HandwritingClassificationOutcome.UNCERTAIN
    decision_ok = decide_routing_outcome([0.10, 0.10], THRESH)
    assert decision_ok.outcome is HandwritingClassificationOutcome.PRINTED


def test_routing_rejects_nan_and_inf() -> None:
    for bad in ([float("nan"), 0.1], [float("inf"), 0.0], [0.5], [0.5, 0.5, 0.5]):
        decision = decide_routing_outcome(bad, THRESH)
        assert decision.outcome is HandwritingClassificationOutcome.UNCERTAIN
        assert decision.decision_reason is HandwritingDecisionReason.INVALID_OUTPUT


def test_fixture_package_verifies_with_allow_flag() -> None:
    assert FIXTURE_DIR.is_dir()
    result = verify_classifier_package(FIXTURE_DIR, allow_test_fixture=True)
    assert result.ready is True
    assert result.checksum_ok is True
    assert result.runtime_provider == "CPUExecutionProvider"
    assert result.record is not None
    assert result.record.is_dual_risk is True


def test_test_fixture_rejected_for_production() -> None:
    result = verify_classifier_package(FIXTURE_DIR, allow_test_fixture=False)
    assert result.ready is False
    assert result.failure_code is VerificationFailureCode.TEST_FIXTURE_NOT_ALLOWED


def test_checksum_mismatch_detected(tmp_path: Path) -> None:
    dest = tmp_path / "pkg"
    dest.mkdir()
    for name in ("model.onnx", "labels.json", "model-record.json", "metrics.json"):
        (dest / name).write_bytes((FIXTURE_DIR / name).read_bytes())
    model = dest / "model.onnx"
    model.write_bytes(model.read_bytes() + b"\x00")
    result = verify_classifier_package(dest, allow_test_fixture=True)
    assert result.ready is False
    assert result.failure_code is VerificationFailureCode.CHECKSUM_MISMATCH


def test_labels_reject_uncertain_as_output(tmp_path: Path) -> None:
    dest = tmp_path / "pkg"
    dest.mkdir()
    for name in ("model.onnx", "model-record.json", "metrics.json"):
        (dest / name).write_bytes((FIXTURE_DIR / name).read_bytes())
    (dest / "labels.json").write_text(
        json.dumps(
            {
                "output_semantics": "independent_binary_risk_logits",
                "outputs": ["handwriting_risk", "uncertain"],
                "public_outcomes": ["printed", "handwritten", "uncertain", "non_text"],
            }
        ),
        encoding="utf-8",
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
        handwriting_accept_threshold=0.70,
        handwriting_safe_low_threshold=0.20,
        non_text_accept_threshold=0.70,
        non_text_safe_low_threshold=0.20,
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


def test_disabled_router_returns_not_run() -> None:
    settings = Settings(
        handwriting_router_enabled=False,
        handwriting_classifier_path=FIXTURE_DIR,
        ocr_enabled=False,
    )
    service = HandwritingClassifierService(settings)
    image = Image.new("RGB", (32, 32), color=(100, 100, 100))
    result = service.classify_crop(image, allow_test_fixture=True)
    assert result.lifecycle is HandwritingClassificationLifecycle.NOT_RUN
    assert result.outcome is None
    assert result.decision_reason is HandwritingDecisionReason.ROUTER_DISABLED


def test_missing_package_unavailable() -> None:
    settings = Settings(
        handwriting_router_enabled=True,
        handwriting_classifier_path=Path("/nonexistent/handwriting_pkg"),
        ocr_enabled=False,
    )
    service = HandwritingClassifierService(settings)
    image = Image.new("RGB", (32, 32), color=(10, 10, 10))
    result = service.classify_crop(image, allow_test_fixture=True)
    assert result.lifecycle is HandwritingClassificationLifecycle.UNAVAILABLE
    assert result.outcome is HandwritingClassificationOutcome.UNCERTAIN

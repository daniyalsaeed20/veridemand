"""Reusable ONNX Runtime handwriting classifier service (Task 2 foundation).

Not invoked from Phase 4 OCR workers or repair paths in Task 2.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from backend.app.contracts.ocr import (
    HandwritingClassificationEvidence,
    HandwritingClassificationLifecycle,
    HandwritingClassificationOutcome,
    HandwritingDecisionReason,
    HandwritingInferenceSource,
)
from backend.app.extraction.handwriting_router.constants import (
    CPU_EXECUTION_PROVIDER,
    EXPECTED_MODEL_LABELS,
    MODEL_ONNX_NAME,
    PROBABILITY_SUM_TOLERANCE,
)
from backend.app.extraction.handwriting_router.manifest import (
    HandwritingModelRecord,
    OutputSemantics,
)
from backend.app.extraction.handwriting_router.preprocess import (
    PreprocessError,
    preprocess_crop,
    stack_batch,
)
from backend.app.extraction.handwriting_router.routing import (
    RoutingThresholds,
    decide_routing_outcome,
)
from backend.app.extraction.handwriting_router.verifier import (
    PackageVerificationResult,
    VerificationFailureCode,
    package_directory_from_path,
    verify_classifier_package,
)
from backend.app.settings.config import Settings
from PIL import Image


@dataclass(frozen=True, slots=True)
class InternalClassificationResult:
    lifecycle: HandwritingClassificationLifecycle
    outcome: HandwritingClassificationOutcome | None
    decision_reason: HandwritingDecisionReason | None
    inference_source: HandwritingInferenceSource | None
    model_version: str | None
    threshold_set_version: str | None
    class_scores: dict[str, float] | None
    top_class: str | None
    top_score: float | None
    second_score: float | None
    class_margin: float | None
    inference_duration_ms: float | None
    region_id: str | None = None

    def to_evidence(self) -> HandwritingClassificationEvidence:
        return HandwritingClassificationEvidence(
            lifecycle=self.lifecycle,
            outcome=self.outcome,
            decision_reason=self.decision_reason,
            inference_source=self.inference_source,
            model_version=self.model_version,
            threshold_set_version=self.threshold_set_version,
            region_id=self.region_id,
        )


def _stable_softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=-1, keepdims=True)
    exp = np.exp(shifted)
    denom = np.sum(exp, axis=-1, keepdims=True)
    result: np.ndarray = exp / denom
    return result


def _interpret_output(raw: np.ndarray, semantics: OutputSemantics) -> np.ndarray | None:
    """Return per-class probabilities shaped (N, 3) or None if invalid."""

    arr = np.asarray(raw, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2 or arr.shape[1] != 3:
        return None
    if not np.all(np.isfinite(arr)):
        return None
    if semantics is OutputSemantics.LOGITS:
        return _stable_softmax(arr)
    # Probabilities
    if np.any(arr < -1e-9):
        return None
    sums = arr.sum(axis=1)
    out = arr.copy()
    for i, total in enumerate(sums):
        if abs(float(total) - 1.0) <= PROBABILITY_SUM_TOLERANCE:
            if abs(float(total) - 1.0) > 0:
                out[i] = out[i] / total
        elif abs(float(total) - 1.0) <= 0.05:
            out[i] = out[i] / total
        else:
            return None
    return out


class HandwritingClassifierService:
    """Lazy, reusable CPU ONNX Runtime classifier."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.RLock()
        self._session: Any | None = None
        self._record: HandwritingModelRecord | None = None
        self._verification: PackageVerificationResult | None = None
        self._session_create_count = 0

    @property
    def session_create_count(self) -> int:
        return self._session_create_count

    @property
    def enabled(self) -> bool:
        return bool(self._settings.handwriting_router_enabled)

    @property
    def required(self) -> bool:
        return bool(self._settings.handwriting_classifier_required)

    def package_dir(self) -> Path:
        return package_directory_from_path(self._settings.handwriting_classifier_path)

    def thresholds(self) -> RoutingThresholds:
        return RoutingThresholds(
            printed=float(self._settings.printed_threshold),
            handwritten=float(self._settings.handwriting_threshold),
            non_text=float(self._settings.non_text_threshold),
            minimum_class_margin=float(self._settings.minimum_class_margin),
        )

    def verify_package(
        self, *, allow_test_fixture: bool = False, force: bool = False
    ) -> PackageVerificationResult:
        with self._lock:
            if self._verification is not None and not force:
                return self._verification
            result = verify_classifier_package(
                self.package_dir(),
                allow_test_fixture=allow_test_fixture,
            )
            self._verification = result
            if result.ready and result.record is not None:
                self._record = result.record
            return result

    def readiness_check(
        self, *, allow_test_fixture: bool = False
    ) -> PackageVerificationResult | None:
        """Return verification when enabled; None when disabled."""

        if not self.enabled:
            return None
        return self.verify_package(allow_test_fixture=allow_test_fixture)

    def _ensure_session(self, *, allow_test_fixture: bool = False) -> PackageVerificationResult:
        with self._lock:
            result = self.verify_package(allow_test_fixture=allow_test_fixture)
            if not result.ready or result.record is None:
                return result
            if self._session is not None:
                return result
            try:
                import onnxruntime as ort
            except ImportError:
                fail = PackageVerificationResult(
                    ready=False,
                    model_version=result.model_version,
                    threshold_set_version=result.threshold_set_version,
                    package_status=result.package_status,
                    checksum_ok=result.checksum_ok,
                    runtime_provider=None,
                    failure_code=VerificationFailureCode.RUNTIME_UNAVAILABLE,
                    message="onnxruntime is not importable.",
                    record=result.record,
                )
                self._verification = fail
                return fail
            model_path = self.package_dir() / MODEL_ONNX_NAME
            try:
                self._session = ort.InferenceSession(
                    str(model_path),
                    providers=[CPU_EXECUTION_PROVIDER],
                )
                self._session_create_count += 1
            except Exception as exc:
                fail = PackageVerificationResult(
                    ready=False,
                    model_version=result.model_version,
                    threshold_set_version=result.threshold_set_version,
                    package_status=result.package_status,
                    checksum_ok=result.checksum_ok,
                    runtime_provider=None,
                    failure_code=VerificationFailureCode.SESSION_INIT_FAILED,
                    message=f"Session initialisation failed: {type(exc).__name__}.",
                    record=result.record,
                )
                self._verification = fail
                return fail
            return result

    def close(self) -> None:
        with self._lock:
            self._session = None
            self._record = None
            self._verification = None

    def classify_crop(
        self,
        image: Image.Image,
        *,
        region_id: str | None = None,
        enforced: bool = True,
        allow_test_fixture: bool = False,
    ) -> InternalClassificationResult:
        """Classify one crop. Does not modify geometry."""

        if not self.enabled:
            return InternalClassificationResult(
                lifecycle=HandwritingClassificationLifecycle.NOT_RUN,
                outcome=None,
                decision_reason=HandwritingDecisionReason.ROUTER_DISABLED,
                inference_source=None,
                model_version=None,
                threshold_set_version=None,
                class_scores=None,
                top_class=None,
                top_score=None,
                second_score=None,
                class_margin=None,
                inference_duration_ms=None,
                region_id=region_id,
            )

        started = time.perf_counter()
        ensure = self._ensure_session(allow_test_fixture=allow_test_fixture)
        if not ensure.ready or self._session is None or self._record is None:
            return self._unavailable(region_id=region_id, enforced=enforced, verify=ensure)

        try:
            tensor = preprocess_crop(image, self._record)
        except PreprocessError:
            return InternalClassificationResult(
                lifecycle=HandwritingClassificationLifecycle.FAILED,
                outcome=HandwritingClassificationOutcome.UNCERTAIN if enforced else None,
                decision_reason=HandwritingDecisionReason.INVALID_INPUT,
                inference_source=HandwritingInferenceSource.SAFETY_ABSTENTION,
                model_version=self._record.model_version,
                threshold_set_version=self._record.threshold_set_version,
                class_scores=None,
                top_class=None,
                top_score=None,
                second_score=None,
                class_margin=None,
                inference_duration_ms=(time.perf_counter() - started) * 1000.0,
                region_id=region_id,
            )

        try:
            with self._lock:
                session = self._session
                record = self._record
                assert session is not None and record is not None
                raw = session.run(
                    [record.output_tensor_name],
                    {record.input_tensor_name: tensor},
                )[0]
        except Exception:
            return InternalClassificationResult(
                lifecycle=HandwritingClassificationLifecycle.FAILED,
                outcome=HandwritingClassificationOutcome.UNCERTAIN if enforced else None,
                decision_reason=HandwritingDecisionReason.INFERENCE_FAILED,
                inference_source=HandwritingInferenceSource.SAFETY_ABSTENTION,
                model_version=self._record.model_version if self._record else None,
                threshold_set_version=(
                    self._record.threshold_set_version if self._record else None
                ),
                class_scores=None,
                top_class=None,
                top_score=None,
                second_score=None,
                class_margin=None,
                inference_duration_ms=(time.perf_counter() - started) * 1000.0,
                region_id=region_id,
            )

        probs = _interpret_output(raw, self._record.output_semantics)
        if probs is None:
            return InternalClassificationResult(
                lifecycle=HandwritingClassificationLifecycle.FAILED,
                outcome=HandwritingClassificationOutcome.UNCERTAIN if enforced else None,
                decision_reason=HandwritingDecisionReason.INVALID_OUTPUT,
                inference_source=HandwritingInferenceSource.SAFETY_ABSTENTION,
                model_version=self._record.model_version,
                threshold_set_version=self._record.threshold_set_version,
                class_scores=None,
                top_class=None,
                top_score=None,
                second_score=None,
                class_margin=None,
                inference_duration_ms=(time.perf_counter() - started) * 1000.0,
                region_id=region_id,
            )

        decision = decide_routing_outcome(probs[0], self.thresholds())
        return InternalClassificationResult(
            lifecycle=decision.lifecycle,
            outcome=decision.outcome,
            decision_reason=decision.decision_reason,
            inference_source=decision.inference_source,
            model_version=self._record.model_version,
            threshold_set_version=self._record.threshold_set_version,
            class_scores=decision.class_scores,
            top_class=decision.top_class,
            top_score=decision.top_score,
            second_score=decision.second_score,
            class_margin=decision.class_margin,
            inference_duration_ms=(time.perf_counter() - started) * 1000.0,
            region_id=region_id,
        )

    def classify_crops(
        self,
        images: list[Image.Image],
        *,
        region_ids: list[str | None] | None = None,
        enforced: bool = True,
        allow_test_fixture: bool = False,
    ) -> list[InternalClassificationResult]:
        ids = region_ids or [None] * len(images)
        if len(ids) != len(images):
            raise ValueError("region_ids length must match images.")
        # Batch preprocess then one session.run when possible.
        if not self.enabled or not images:
            return [
                self.classify_crop(
                    img, region_id=rid, enforced=enforced, allow_test_fixture=allow_test_fixture
                )
                for img, rid in zip(images, ids, strict=True)
            ]

        ensure = self._ensure_session(allow_test_fixture=allow_test_fixture)
        if not ensure.ready or self._session is None or self._record is None:
            return [
                self._unavailable(region_id=rid, enforced=enforced, verify=ensure) for rid in ids
            ]

        batch_size = max(1, int(self._settings.handwriting_classifier_batch_size))
        results: list[InternalClassificationResult] = []
        for start in range(0, len(images), batch_size):
            chunk = images[start : start + batch_size]
            chunk_ids = ids[start : start + batch_size]
            tensors: list[np.ndarray] = []
            ok_indices: list[int] = []
            pending: list[InternalClassificationResult | None] = [None] * len(chunk)
            for i, image in enumerate(chunk):
                try:
                    tensors.append(preprocess_crop(image, self._record))
                    ok_indices.append(i)
                except PreprocessError:
                    pending[i] = InternalClassificationResult(
                        lifecycle=HandwritingClassificationLifecycle.FAILED,
                        outcome=(HandwritingClassificationOutcome.UNCERTAIN if enforced else None),
                        decision_reason=HandwritingDecisionReason.INVALID_INPUT,
                        inference_source=HandwritingInferenceSource.SAFETY_ABSTENTION,
                        model_version=self._record.model_version,
                        threshold_set_version=self._record.threshold_set_version,
                        class_scores=None,
                        top_class=None,
                        top_score=None,
                        second_score=None,
                        class_margin=None,
                        inference_duration_ms=None,
                        region_id=chunk_ids[i],
                    )
            if tensors:
                batch = stack_batch(tensors)
                try:
                    with self._lock:
                        session = self._session
                        record = self._record
                        assert session is not None and record is not None
                        raw = session.run(
                            [record.output_tensor_name],
                            {record.input_tensor_name: batch},
                        )[0]
                except Exception:
                    for i in ok_indices:
                        pending[i] = InternalClassificationResult(
                            lifecycle=HandwritingClassificationLifecycle.FAILED,
                            outcome=(
                                HandwritingClassificationOutcome.UNCERTAIN if enforced else None
                            ),
                            decision_reason=HandwritingDecisionReason.INFERENCE_FAILED,
                            inference_source=HandwritingInferenceSource.SAFETY_ABSTENTION,
                            model_version=self._record.model_version,
                            threshold_set_version=self._record.threshold_set_version,
                            class_scores=None,
                            top_class=None,
                            top_score=None,
                            second_score=None,
                            class_margin=None,
                            inference_duration_ms=None,
                            region_id=chunk_ids[i],
                        )
                else:
                    probs = _interpret_output(raw, self._record.output_semantics)
                    if probs is None or probs.shape[0] != len(ok_indices):
                        for i in ok_indices:
                            pending[i] = InternalClassificationResult(
                                lifecycle=HandwritingClassificationLifecycle.FAILED,
                                outcome=(
                                    HandwritingClassificationOutcome.UNCERTAIN if enforced else None
                                ),
                                decision_reason=HandwritingDecisionReason.INVALID_OUTPUT,
                                inference_source=HandwritingInferenceSource.SAFETY_ABSTENTION,
                                model_version=self._record.model_version,
                                threshold_set_version=self._record.threshold_set_version,
                                class_scores=None,
                                top_class=None,
                                top_score=None,
                                second_score=None,
                                class_margin=None,
                                inference_duration_ms=None,
                                region_id=chunk_ids[i],
                            )
                    else:
                        for local_j, i in enumerate(ok_indices):
                            decision = decide_routing_outcome(probs[local_j], self.thresholds())
                            pending[i] = InternalClassificationResult(
                                lifecycle=decision.lifecycle,
                                outcome=decision.outcome,
                                decision_reason=decision.decision_reason,
                                inference_source=decision.inference_source,
                                model_version=self._record.model_version,
                                threshold_set_version=self._record.threshold_set_version,
                                class_scores=decision.class_scores,
                                top_class=decision.top_class,
                                top_score=decision.top_score,
                                second_score=decision.second_score,
                                class_margin=decision.class_margin,
                                inference_duration_ms=None,
                                region_id=chunk_ids[i],
                            )
            for item in pending:
                assert item is not None
                results.append(item)
        return results

    def _unavailable(
        self,
        *,
        region_id: str | None,
        enforced: bool,
        verify: PackageVerificationResult,
    ) -> InternalClassificationResult:
        reason = HandwritingDecisionReason.MODEL_UNAVAILABLE
        verification_failed = {
            VerificationFailureCode.CHECKSUM_MISMATCH,
            VerificationFailureCode.MANIFEST_INVALID,
            VerificationFailureCode.LABELS_INVALID,
            VerificationFailureCode.ONNX_STRUCTURAL_INVALID,
        }
        if verify.failure_code in verification_failed:
            reason = HandwritingDecisionReason.MODEL_VERIFICATION_FAILED
        return InternalClassificationResult(
            lifecycle=HandwritingClassificationLifecycle.UNAVAILABLE,
            outcome=HandwritingClassificationOutcome.UNCERTAIN if enforced else None,
            decision_reason=reason,
            inference_source=HandwritingInferenceSource.SAFETY_ABSTENTION,
            model_version=verify.model_version,
            threshold_set_version=verify.threshold_set_version,
            class_scores={label: float("nan") for label in EXPECTED_MODEL_LABELS},
            top_class=None,
            top_score=None,
            second_score=None,
            class_margin=None,
            inference_duration_ms=None,
            region_id=region_id,
        )

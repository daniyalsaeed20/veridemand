"""Runtime-only route-aware ETA estimation (Phase 4.5).

Never persists user-document performance data. Estimates are process-local.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from backend.app.contracts.routing import EstimateStatus, PageRoute


class EtaCostRoute(StrEnum):
    """Cost classes tracked separately for ETA."""

    DIGITAL_NATIVE = "digital_native"
    EMBEDDED_OCR_VISUAL_CHECK = "embedded_ocr_visual_check"
    EMBEDDED_OCR_RECOGNITION_CHECK = "embedded_ocr_recognition_check"
    TARGETED_REPAIR = "targeted_repair"
    FULL_OCR_PRIMARY = "full_ocr_primary"
    FULL_OCR_FALLBACK = "full_ocr_fallback"


def page_route_to_cost_route(route: PageRoute | str) -> EtaCostRoute:
    value = route.value if isinstance(route, PageRoute) else str(route)
    mapping = {
        PageRoute.DIGITAL_NATIVE.value: EtaCostRoute.DIGITAL_NATIVE,
        PageRoute.EMBEDDED_OCR_VERIFIED.value: EtaCostRoute.EMBEDDED_OCR_VISUAL_CHECK,
        PageRoute.EMBEDDED_OCR_TARGETED_REPAIR.value: EtaCostRoute.TARGETED_REPAIR,
        PageRoute.FULL_VISUAL_OCR.value: EtaCostRoute.FULL_OCR_PRIMARY,
        PageRoute.VISUAL_NO_TEXT.value: EtaCostRoute.DIGITAL_NATIVE,
    }
    return mapping.get(value, EtaCostRoute.FULL_OCR_PRIMARY)


@dataclass(slots=True)
class _RouteStats:
    samples: list[float] = field(default_factory=list)
    ewma: float | None = None

    def add(self, seconds: float, *, max_samples: int = 64) -> None:
        if seconds < 0:
            return
        self.samples.append(float(seconds))
        if len(self.samples) > max_samples:
            self.samples = self.samples[-max_samples:]
        alpha = 0.25
        self.ewma = seconds if self.ewma is None else (alpha * seconds + (1 - alpha) * self.ewma)

    def robust_mean(self) -> float | None:
        if not self.samples:
            return None
        if len(self.samples) == 1:
            return self.samples[0]
        ordered = sorted(self.samples)
        # Trimmed mean: drop min/max when enough samples.
        trimmed = ordered[1:-1] if len(ordered) >= 4 else ordered
        median = statistics.median(trimmed)
        mean = statistics.fmean(trimmed)
        if self.ewma is None:
            return 0.5 * median + 0.5 * mean
        return 0.4 * median + 0.3 * mean + 0.3 * self.ewma


@dataclass(slots=True)
class EtaSnapshot:
    estimate_status: EstimateStatus
    estimate_sample_count: int
    estimated_current_operation_seconds: float | None
    estimated_current_page_seconds: float | None
    estimated_document_remaining_seconds: float | None
    estimated_queue_remaining_seconds: float | None
    estimated_completion_at: datetime | None
    estimate_confidence: str | None
    average_page_seconds: float | None
    average_full_ocr_page_seconds: float | None
    pages_per_minute: float | None


class EtaEstimator:
    """Route-aware rolling ETA estimator (runtime only)."""

    def __init__(
        self, *, minimum_sample_count: int = 3, stale_after_seconds: float = 120.0
    ) -> None:
        self._minimum = max(1, minimum_sample_count)
        self._stale_after = stale_after_seconds
        self._by_route: dict[EtaCostRoute, _RouteStats] = {r: _RouteStats() for r in EtaCostRoute}
        self._last_update_monotonic = time.monotonic()
        self._complete = False

    def record(self, route: EtaCostRoute | PageRoute | str, duration_seconds: float) -> None:
        if self._complete:
            return
        cost = route if isinstance(route, EtaCostRoute) else page_route_to_cost_route(route)
        self._by_route[cost].add(duration_seconds)
        self._last_update_monotonic = time.monotonic()

    def remove_cancelled(self) -> None:
        """Cancellation does not rewrite history; mark for recalculation only."""

        self._last_update_monotonic = time.monotonic()

    def mark_complete(self) -> None:
        self._complete = True

    def reset(self) -> None:
        self._by_route = {r: _RouteStats() for r in EtaCostRoute}
        self._complete = False
        self._last_update_monotonic = time.monotonic()

    @property
    def sample_count(self) -> int:
        return sum(len(stats.samples) for stats in self._by_route.values())

    def estimate(
        self,
        *,
        remaining_by_route: dict[EtaCostRoute, int] | None = None,
        queue_remaining_by_route: dict[EtaCostRoute, int] | None = None,
        current_operation_route: EtaCostRoute | None = None,
        current_page_route: EtaCostRoute | None = None,
    ) -> EtaSnapshot:
        if self._complete:
            return EtaSnapshot(
                estimate_status=EstimateStatus.COMPLETE,
                estimate_sample_count=self.sample_count,
                estimated_current_operation_seconds=0.0,
                estimated_current_page_seconds=0.0,
                estimated_document_remaining_seconds=0.0,
                estimated_queue_remaining_seconds=0.0,
                estimated_completion_at=datetime.now(UTC),
                estimate_confidence="high",
                average_page_seconds=self._average_all(),
                average_full_ocr_page_seconds=self._by_route[
                    EtaCostRoute.FULL_OCR_PRIMARY
                ].robust_mean(),
                pages_per_minute=self._pages_per_minute(),
            )

        age = time.monotonic() - self._last_update_monotonic
        if self.sample_count == 0:
            status = EstimateStatus.UNAVAILABLE
        elif self.sample_count < self._minimum:
            status = EstimateStatus.COLLECTING_SAMPLES
        elif age > self._stale_after:
            status = EstimateStatus.STALE
        else:
            status = EstimateStatus.AVAILABLE

        doc_remaining = self._sum_remaining(remaining_by_route or {})
        queue_remaining = self._sum_remaining(queue_remaining_by_route or {})
        if doc_remaining is not None:
            doc_remaining = max(0.0, doc_remaining)
        if queue_remaining is not None:
            queue_remaining = max(0.0, queue_remaining)

        confidence = None
        if status is EstimateStatus.AVAILABLE:
            confidence = "high" if self.sample_count >= self._minimum * 3 else "medium"
        elif status is EstimateStatus.COLLECTING_SAMPLES or status is EstimateStatus.STALE:
            confidence = "low"

        completion_at = None
        if doc_remaining is not None and status in {
            EstimateStatus.AVAILABLE,
            EstimateStatus.STALE,
            EstimateStatus.RECALCULATING,
        }:
            from datetime import timedelta

            completion_at = datetime.now(UTC) + timedelta(seconds=doc_remaining)

        cur_op = (
            self._by_route[current_operation_route].robust_mean()
            if current_operation_route is not None
            else None
        )
        cur_page = (
            self._by_route[current_page_route].robust_mean()
            if current_page_route is not None
            else None
        )

        return EtaSnapshot(
            estimate_status=status,
            estimate_sample_count=self.sample_count,
            estimated_current_operation_seconds=cur_op,
            estimated_current_page_seconds=cur_page,
            estimated_document_remaining_seconds=doc_remaining
            if status not in {EstimateStatus.UNAVAILABLE, EstimateStatus.COLLECTING_SAMPLES}
            else None,
            estimated_queue_remaining_seconds=queue_remaining
            if status not in {EstimateStatus.UNAVAILABLE, EstimateStatus.COLLECTING_SAMPLES}
            else None,
            estimated_completion_at=completion_at,
            estimate_confidence=confidence,
            average_page_seconds=self._average_all(),
            average_full_ocr_page_seconds=self._by_route[
                EtaCostRoute.FULL_OCR_PRIMARY
            ].robust_mean(),
            pages_per_minute=self._pages_per_minute(),
        )

    def _sum_remaining(self, remaining: dict[EtaCostRoute, int]) -> float | None:
        if not remaining:
            return 0.0
        if all(count <= 0 for count in remaining.values()):
            return 0.0
        total = 0.0
        any_known = False
        for route, count in remaining.items():
            if count <= 0:
                continue
            mean = self._by_route[route].robust_mean()
            if mean is None:
                # Fall back to full OCR primary mean when route unseen.
                mean = self._by_route[EtaCostRoute.FULL_OCR_PRIMARY].robust_mean()
            if mean is None:
                continue
            any_known = True
            total += mean * count
        return total if any_known else None

    def _average_all(self) -> float | None:
        values = [s for stats in self._by_route.values() for s in stats.samples]
        if not values:
            return None
        return statistics.fmean(values)

    def _pages_per_minute(self) -> float | None:
        full = self._by_route[EtaCostRoute.FULL_OCR_PRIMARY].robust_mean()
        if full is None or full <= 0:
            return None
        return 60.0 / full

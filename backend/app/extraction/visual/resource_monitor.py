"""Worker process RSS monitoring and recycle decisions."""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("veridemand.visual.resource_monitor")


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    """Privacy-safe resource sample for one worker process."""

    rss_mb: float
    pages_since_start: int
    recycle_recommended: bool


class ResourceMonitor:
    """Track worker RSS and page throughput for recycle decisions."""

    def __init__(
        self,
        *,
        max_rss_mb: float,
        recycle_after_pages: int,
        pid: int | None = None,
    ) -> None:
        self._max_rss_mb = max_rss_mb
        self._recycle_after_pages = recycle_after_pages
        self._pid = pid
        self._pages_since_start = 0

    def note_page_completed(self) -> None:
        self._pages_since_start += 1

    @property
    def pages_since_start(self) -> int:
        return self._pages_since_start

    def reset_after_recycle(self, *, pid: int | None) -> None:
        self._pid = pid
        self._pages_since_start = 0

    def snapshot(self) -> ResourceSnapshot:
        rss_mb = self.current_rss_mb()
        recycle = False
        if rss_mb is not None and rss_mb >= self._max_rss_mb:
            recycle = True
        if self._pages_since_start >= self._recycle_after_pages:
            recycle = True
        return ResourceSnapshot(
            rss_mb=rss_mb if rss_mb is not None else 0.0,
            pages_since_start=self._pages_since_start,
            recycle_recommended=recycle,
        )

    def current_rss_mb(self) -> float | None:
        if self._pid is None:
            return _self_rss_mb()
        try:
            import psutil

            process = psutil.Process(self._pid)
            return float(process.memory_info().rss) / (1024.0 * 1024.0)
        except Exception:
            logger.warning("Failed to sample worker RSS", extra={"pid": self._pid})
            return None


def _self_rss_mb() -> float | None:
    try:
        import psutil

        return float(psutil.Process().memory_info().rss) / (1024.0 * 1024.0)
    except Exception:
        return None

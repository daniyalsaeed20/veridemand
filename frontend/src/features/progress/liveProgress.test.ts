import { afterEach, describe, expect, it, vi } from "vitest";

import { deriveLiveProgress } from "./deriveLiveProgress";
import { formatDuration } from "./formatDuration";
import { formatEta } from "./formatEta";
import { liveProgressClockStore } from "./liveProgressClockStore";

describe("live progress clock", () => {
  afterEach(() => {
    liveProgressClockStore._resetForTests();
    vi.useRealTimers();
  });

  it("acquires a single shared interval", () => {
    vi.useFakeTimers();
    liveProgressClockStore.acquire();
    liveProgressClockStore.acquire();
    expect(liveProgressClockStore._hasIntervalForTests()).toBe(true);
    expect(liveProgressClockStore._activeCountForTests()).toBe(2);
    liveProgressClockStore.release();
    expect(liveProgressClockStore._hasIntervalForTests()).toBe(true);
    liveProgressClockStore.release();
    expect(liveProgressClockStore._hasIntervalForTests()).toBe(false);
  });

  it("pauses ticker when tab is hidden", () => {
    vi.useFakeTimers();
    liveProgressClockStore.acquire();
    expect(liveProgressClockStore._hasIntervalForTests()).toBe(true);
    liveProgressClockStore.setHidden(true);
    expect(liveProgressClockStore._hasIntervalForTests()).toBe(false);
    liveProgressClockStore.setHidden(false);
    expect(liveProgressClockStore._hasIntervalForTests()).toBe(true);
  });
});

describe("deriveLiveProgress", () => {
  it("increments elapsed without a new SSE snapshot", () => {
    const view = deriveLiveProgress(
      {
        document_elapsed_seconds: 10,
        page_elapsed_seconds: 5,
        estimated_document_remaining_seconds: 100,
        estimate_status: "available",
        status: "visual_processing",
      },
      {
        receivedAtMonotonic: 0,
        nowMonotonic: 3000,
        active: true,
      },
    );
    expect(view.liveDocumentElapsed).toBeCloseTo(13);
    expect(view.livePageElapsed).toBeCloseTo(8);
    expect(view.liveRemaining).toBeCloseTo(97);
  });

  it("never reports negative remaining and shows recalculating when overdue", () => {
    const eta = formatEta(0, "available");
    expect(eta.kind).toBe("recalculating");
    const view = deriveLiveProgress(
      {
        document_elapsed_seconds: 10,
        estimated_document_remaining_seconds: 1,
        estimate_status: "available",
        status: "visual_processing",
      },
      { receivedAtMonotonic: 0, nowMonotonic: 5000, active: true },
    );
    expect(view.liveRemaining).toBe(0);
    expect(view.eta.kind).toBe("recalculating");
  });

  it("shows calculating when estimate unavailable", () => {
    const eta = formatEta(null, "collecting_samples");
    expect(eta.label).toBe("Calculating estimate…");
  });
});

describe("formatDuration", () => {
  it("formats minutes and seconds", () => {
    expect(formatDuration(65)).toContain("minute");
    expect(formatDuration(5)).toBe("5 seconds");
  });
});

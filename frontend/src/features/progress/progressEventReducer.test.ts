import { afterEach, describe, expect, it, vi } from "vitest";

import { initialProgressReducerState, reduceProgressEvent } from "./progressEventReducer";
import { liveProgressClockStore } from "./liveProgressClockStore";
import { deriveLiveProgress } from "./deriveLiveProgress";

describe("progressEventReducer", () => {
  it("rejects lower event_sequence", () => {
    const first = reduceProgressEvent(initialProgressReducerState, {
      event_sequence: 5,
      progress_version: 2,
      document_id: "doc_1",
      event: "document.visual_page_started",
      operation_status: "started",
      attempt_number: 1,
      overall_percent: 40,
    });
    expect(first.accepted).toBe(true);
    const stale = reduceProgressEvent(first.state, {
      event_sequence: 3,
      progress_version: 3,
      document_id: "doc_1",
      event: "document.visual_page_ocr_started",
      operation_status: "started",
      attempt_number: 1,
      overall_percent: 50,
    });
    expect(stale.accepted).toBe(false);
    expect(stale.reason).toBe("stale_event_rejected");
  });

  it("rejects lower progress_version for non-heartbeat", () => {
    const first = reduceProgressEvent(initialProgressReducerState, {
      event_sequence: 1,
      progress_version: 4,
      document_id: "doc_1",
      event: "document.visual_page_started",
      overall_percent: 42,
    });
    const stale = reduceProgressEvent(first.state, {
      event_sequence: 2,
      progress_version: 2,
      document_id: "doc_1",
      event: "document.visual_page_rendered",
      overall_percent: 44,
    });
    expect(stale.accepted).toBe(false);
  });

  it("rejects terminal to active regression", () => {
    const done = reduceProgressEvent(initialProgressReducerState, {
      event_sequence: 1,
      progress_version: 1,
      document_id: "doc_1",
      event: "document.visual_processing_completed",
      operation_status: "completed",
      attempt_number: 1,
      overall_percent: 65,
    });
    const regress = reduceProgressEvent(done.state, {
      event_sequence: 2,
      progress_version: 2,
      document_id: "doc_1",
      event: "document.visual_page_started",
      operation_status: "started",
      attempt_number: 1,
      overall_percent: 50,
    });
    expect(regress.accepted).toBe(false);
    expect(regress.reason).toBe("invalid_lifecycle_transition");
  });

  it("accepts full_ocr primary completed then quality evaluation started", () => {
    let state = initialProgressReducerState;
    const steps = [
      {
        event_sequence: 1,
        progress_version: 1,
        document_id: "doc_1",
        event: "document.full_ocr_primary_started",
        operation_id: "op_primary",
        operation_status: "started",
        attempt_number: 1,
        document_page_number: 1,
        overall_percent: 40,
      },
      {
        event_sequence: 2,
        progress_version: 2,
        document_id: "doc_1",
        event: "document.full_ocr_primary_completed",
        operation_id: "op_primary",
        operation_status: "completed",
        attempt_number: 1,
        document_page_number: 1,
        overall_percent: 45,
      },
      {
        event_sequence: 3,
        progress_version: 3,
        document_id: "doc_1",
        event: "document.full_ocr_quality_evaluation_started",
        operation_id: "op_quality",
        operation_status: "started",
        attempt_number: 1,
        document_page_number: 1,
        overall_percent: 48,
      },
      {
        event_sequence: 4,
        progress_version: 4,
        document_id: "doc_1",
        event: "document.full_ocr_result_selection_started",
        operation_id: "op_select",
        operation_status: "started",
        attempt_number: 1,
        document_page_number: 1,
        overall_percent: 52,
      },
    ] as const;
    for (const step of steps) {
      const result = reduceProgressEvent(state, step);
      expect(result.accepted).toBe(true);
      state = result.state;
    }
    expect(state.byDocument.doc_1?.terminal).toBe(false);
  });

  it("accepts page N completed then page N+1 visual_page_started", () => {
    const page1Done = reduceProgressEvent(initialProgressReducerState, {
      event_sequence: 1,
      progress_version: 1,
      document_id: "doc_1",
      event: "document.visual_page_ocr_completed",
      operation_id: "op_page_1",
      operation_status: "completed",
      attempt_number: 1,
      document_page_number: 1,
      overall_percent: 40,
    });
    expect(page1Done.accepted).toBe(true);
    const page2Start = reduceProgressEvent(page1Done.state, {
      event_sequence: 2,
      progress_version: 2,
      document_id: "doc_1",
      event: "document.visual_page_started",
      operation_id: "op_page_2",
      operation_status: "started",
      attempt_number: 1,
      document_page_number: 2,
      overall_percent: 42,
    });
    expect(page2Start.accepted).toBe(true);
    expect(page2Start.state.byDocument.doc_1?.terminal).toBe(false);
  });

  it("clears native terminal on visual_processing_started", () => {
    const nativeDone = reduceProgressEvent(initialProgressReducerState, {
      event_sequence: 1,
      progress_version: 1,
      document_id: "doc_1",
      event: "document.native_extraction_completed",
      operation_id: "op_native",
      operation_status: "completed",
      attempt_number: 1,
      overall_percent: 32,
    });
    expect(nativeDone.state.byDocument.doc_1?.terminal).toBe(true);
    const visualStart = reduceProgressEvent(nativeDone.state, {
      event_sequence: 2,
      progress_version: 2,
      document_id: "doc_1",
      event: "document.visual_processing_started",
      operation_id: "op_visual",
      operation_status: "started",
      attempt_number: 1,
      overall_percent: 35,
    });
    expect(visualStart.accepted).toBe(true);
    expect(visualStart.state.byDocument.doc_1?.terminal).toBe(false);
  });

  it("rejects same operation_id terminal to active regression", () => {
    const done = reduceProgressEvent(initialProgressReducerState, {
      event_sequence: 1,
      progress_version: 1,
      document_id: "doc_1",
      event: "document.full_ocr_primary_completed",
      operation_id: "op_same",
      operation_status: "completed",
      attempt_number: 1,
      overall_percent: 40,
    });
    const regress = reduceProgressEvent(done.state, {
      event_sequence: 2,
      progress_version: 2,
      document_id: "doc_1",
      event: "document.full_ocr_primary_started",
      operation_id: "op_same",
      operation_status: "started",
      attempt_number: 1,
      overall_percent: 40,
    });
    expect(regress.accepted).toBe(false);
    expect(regress.reason).toBe("invalid_lifecycle_transition");
  });
});

describe("live progress clocks", () => {
  afterEach(() => {
    liveProgressClockStore._resetForTests();
    vi.useRealTimers();
  });

  it("uses one shared ticker and pauses when hidden", () => {
    vi.useFakeTimers();
    liveProgressClockStore.acquire();
    expect(liveProgressClockStore._hasIntervalForTests()).toBe(true);
    liveProgressClockStore.acquire();
    expect(liveProgressClockStore._activeCountForTests()).toBe(2);
    liveProgressClockStore.setHidden(true);
    expect(liveProgressClockStore._hasIntervalForTests()).toBe(false);
    liveProgressClockStore.setHidden(false);
    expect(liveProgressClockStore._hasIntervalForTests()).toBe(true);
    liveProgressClockStore.release();
    liveProgressClockStore.release();
    expect(liveProgressClockStore._hasIntervalForTests()).toBe(false);
  });

  it("never shows negative remaining and recalculates when overdue", () => {
    const view = deriveLiveProgress(
      {
        document_elapsed_seconds: 10,
        page_elapsed_seconds: 2,
        operation_elapsed_seconds: 1,
        estimated_document_remaining_seconds: 3,
        estimate_status: "available",
      },
      { receivedAtMonotonic: 0, nowMonotonic: 5000, active: true },
    );
    expect(view.liveRemaining).toBe(0);
    expect(view.eta.kind).toBe("recalculating");
    expect(view.documentElapsedLabel).not.toContain("-");
  });

  it("updates batch and document elapsed independently", () => {
    const view = deriveLiveProgress(
      {
        batch_elapsed_seconds: 100,
        document_elapsed_seconds: 20,
        page_elapsed_seconds: 5,
        operation_elapsed_seconds: 2,
        estimated_document_remaining_seconds: 50,
        estimated_batch_remaining_seconds: 200,
        estimate_status: "available",
      },
      { receivedAtMonotonic: 0, nowMonotonic: 1000, active: true },
    );
    expect(view.liveDocumentElapsed).toBe(21);
    expect(view.batchElapsedLabel).toContain("1");
  });
});

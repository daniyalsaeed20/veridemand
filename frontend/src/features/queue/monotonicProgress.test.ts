import { describe, expect, it } from "vitest";

import { applyMonotonicProgress } from "./monotonicProgress";
import type { DocumentSummary } from "../viewer/viewerApi";

function baseDoc(overrides: Partial<DocumentSummary> = {}): DocumentSummary {
  return {
    document_id: "doc_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    display_filename: "x.pdf",
    extension: "pdf",
    format: "pdf",
    media_type: "application/pdf",
    size_bytes: 10,
    sha256: "a".repeat(64),
    page_count: 2,
    page_count_status: "known",
    status: "visual_processing",
    progress_percent: 41,
    result_available: false,
    extraction_performed: false,
    native_extraction_performed: true,
    native_result_available: false,
    visual_processing_required: true,
    visual_processing_performed: false,
    visual_result_available: false,
    warning_count: 0,
    created_at: "2026-01-01T00:00:00.000Z",
    canonical_view_available: true,
    major_phase: "visual_ocr",
    major_phase_percent: 20,
    ...overrides,
  };
}

describe("applyMonotonicProgress", () => {
  it("does not let stale native progress overwrite visual progress", () => {
    const first = applyMonotonicProgress(
      baseDoc({ progress_percent: 52, major_phase_percent: 56 }),
      undefined,
    );
    const stale = applyMonotonicProgress(
      baseDoc({ progress_percent: 32, major_phase_percent: 0, status: "extracting_native" }),
      first.floor,
    );
    expect(stale.document.progress_percent).toBe(52);
    expect(stale.document.major_phase_percent).toBe(56);
  });

  it("does not reach 65 before terminal completion", () => {
    const mid = applyMonotonicProgress(
      baseDoc({ progress_percent: 52, major_phase_percent: 56 }),
      undefined,
    );
    expect(mid.document.progress_percent).toBeLessThan(65);
    const done = applyMonotonicProgress(
      baseDoc({
        status: "visual_processing_complete",
        progress_percent: 65,
        major_phase_percent: 100,
      }),
      mid.floor,
    );
    expect(done.document.progress_percent).toBe(65);
  });
});

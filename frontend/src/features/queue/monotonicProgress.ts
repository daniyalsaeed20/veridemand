/** Client-side monotonic progress floors so stale snapshot refetches cannot regress UI. */

import type { DocumentSummary } from "../viewer/viewerApi";

export interface ProgressFloor {
  progress_percent: number;
  major_phase_percent: number;
}

/**
 * Merge a fresh document summary with the previous floor.
 * Overall and major-phase percents never decrease for in-progress documents.
 * Page percent may reset when the active page number changes (trusted from server).
 */
export function applyMonotonicProgress(
  document: DocumentSummary,
  previous: ProgressFloor | undefined,
): { document: DocumentSummary; floor: ProgressFloor } {
  const terminal =
    document.status === "visual_processing_complete" ||
    document.status === "visual_processing_partial" ||
    document.status === "visual_processing_failed" ||
    document.status === "failed" ||
    document.status === "cancelled";

  if (terminal || previous === undefined) {
    const floor: ProgressFloor = {
      progress_percent: document.progress_percent,
      major_phase_percent: document.major_phase_percent ?? 0,
    };
    return { document, floor };
  }

  const progress_percent = Math.max(previous.progress_percent, document.progress_percent);
  const major_phase_percent = Math.max(
    previous.major_phase_percent,
    document.major_phase_percent ?? 0,
  );

  const floor: ProgressFloor = {
    progress_percent,
    major_phase_percent,
  };

  return {
    document: {
      ...document,
      progress_percent,
      major_phase_percent,
    },
    floor,
  };
}

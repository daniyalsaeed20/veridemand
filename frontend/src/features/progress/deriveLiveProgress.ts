import { liveProgressClockStore } from "./liveProgressClockStore";
import { formatDuration } from "./formatDuration";
import { formatEta, type EtaDisplay } from "./formatEta";

export interface ProgressSnapshotInput {
  readonly document_elapsed_seconds?: number | null;
  readonly page_elapsed_seconds?: number | null;
  readonly operation_elapsed_seconds?: number | null;
  readonly estimated_document_remaining_seconds?: number | null;
  readonly estimate_status?: string | null;
  readonly estimate_confidence?: string | null;
  readonly current_route?: string | null;
  readonly current_operation?: string | null;
  readonly operation_status?: string | null;
  readonly major_phase?: string | null;
  readonly major_phase_percent?: number | null;
  readonly progress_percent?: number | null;
  readonly active_page_number?: number | null;
  readonly pages_completed?: number | null;
  readonly pages_total?: number | null;
  readonly pages_remaining?: number | null;
  readonly native_pages_retained?: number | null;
  readonly embedded_ocr_pages_verified?: number | null;
  readonly targeted_repair_pages_selected?: number | null;
  readonly targeted_repair_pages_completed?: number | null;
  readonly full_ocr_pages_selected?: number | null;
  readonly full_ocr_pages_completed?: number | null;
  readonly full_ocr_pages_remaining?: number | null;
  readonly average_full_ocr_page_seconds?: number | null;
  readonly pages_per_minute?: number | null;
  readonly estimated_completion_at?: string | null;
  readonly progress_version?: number | null;
  readonly status?: string | null;
}

export interface LiveProgressView {
  readonly documentElapsedLabel: string;
  readonly pageElapsedLabel: string;
  readonly operationElapsedLabel: string;
  readonly eta: EtaDisplay;
  readonly liveDocumentElapsed: number;
  readonly livePageElapsed: number;
  readonly liveRemaining: number | null;
}

const ACTIVE_STATUSES = new Set([
  "queued",
  "canonicalising",
  "inspecting_native",
  "extracting_native",
  "visual_pending",
  "visual_processing",
]);

export function isProgressActive(status: string | null | undefined): boolean {
  return status != null && ACTIVE_STATUSES.has(status);
}

/**
 * Derive live elapsed/remaining from a backend snapshot + local monotonic clock.
 * Does not mutate backend state.
 */
export function deriveLiveProgress(
  snapshot: ProgressSnapshotInput,
  options: {
    readonly receivedAtMonotonic: number;
    readonly nowMonotonic: number;
    readonly active: boolean;
  },
): LiveProgressView {
  const { receivedAtMonotonic, nowMonotonic, active } = options;
  const deltaSec = active
    ? Math.max(0, (nowMonotonic - receivedAtMonotonic) / 1000)
    : 0;

  const baseDoc = snapshot.document_elapsed_seconds ?? 0;
  const basePage = snapshot.page_elapsed_seconds ?? 0;
  const baseOp = snapshot.operation_elapsed_seconds ?? 0;

  const liveDocumentElapsed = baseDoc + deltaSec;
  const livePageElapsed = basePage + deltaSec;
  const liveOperationElapsed = baseOp + deltaSec;

  const backendRemaining = snapshot.estimated_document_remaining_seconds;
  let liveRemaining: number | null = null;
  if (backendRemaining != null && Number.isFinite(backendRemaining)) {
    liveRemaining = Math.max(0, backendRemaining - deltaSec);
  }

  const eta = formatEta(liveRemaining, snapshot.estimate_status);

  return {
    documentElapsedLabel: formatDuration(liveDocumentElapsed),
    pageElapsedLabel: formatDuration(livePageElapsed),
    operationElapsedLabel: formatDuration(liveOperationElapsed),
    eta,
    liveDocumentElapsed,
    livePageElapsed,
    liveRemaining,
  };
}

export function captureSnapshotReceivedAt(): number {
  return liveProgressClockStore.captureReceivedAt();
}

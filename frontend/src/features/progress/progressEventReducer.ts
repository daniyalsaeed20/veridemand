/** Deterministic progress-event reducer with stale/lifecycle rejection. */

export type ProgressRejectReason =
  "stale_event_rejected" | "duplicate_event_rejected" | "invalid_lifecycle_transition";

export interface ProgressEventLike {
  readonly event_id?: string | null;
  readonly event_sequence?: number | null;
  readonly progress_version?: number | null;
  readonly event?: string | null;
  readonly document_id?: string | null;
  readonly operation?: string | null;
  readonly operation_id?: string | null;
  readonly operation_status?: string | null;
  readonly attempt_number?: number | null;
  readonly document_page_number?: number | null;
  readonly selected_page_index?: number | null;
  readonly overall_percent?: number | null;
  readonly progress_kind?: string | null;
}

export interface DocumentProgressState {
  readonly lastEventSequence: number;
  readonly lastProgressVersion: number;
  readonly operationId: string | null;
  readonly operationStatus: string | null;
  readonly attemptNumber: number;
  readonly documentPageNumber: number | null;
  readonly selectedPageIndex: number | null;
  readonly overallPercent: number;
  readonly terminal: boolean;
  readonly latestEvent: ProgressEventLike | null;
}

export interface ProgressReducerState {
  readonly byDocument: Readonly<Record<string, DocumentProgressState>>;
  readonly lastSessionSequence: number;
}

export interface ProgressReduceResult {
  readonly state: ProgressReducerState;
  readonly accepted: boolean;
  readonly reason?: ProgressRejectReason;
}

const TERMINAL_STATUSES = new Set(["completed", "failed", "timed_out", "cancelled", "skipped"]);

const DOCUMENT_TERMINAL_EVENTS = new Set([
  "document.failed",
  "document.cancelled",
  "document.visual_processing_completed",
  "document.visual_processing_partial",
  "document.visual_processing_failed",
  "document.native_extraction_completed",
]);

export const initialProgressReducerState: ProgressReducerState = {
  byDocument: {},
  lastSessionSequence: 0,
};

function warnDev(reason: ProgressRejectReason, event: ProgressEventLike): void {
  if (typeof process !== "undefined" && process.env.NODE_ENV === "development") {
    // Privacy-safe: no filenames or text content.
    console.warn(reason, {
      event_sequence: event.event_sequence ?? null,
      progress_version: event.progress_version ?? null,
      event: event.event ?? null,
      operation: event.operation ?? null,
      operation_status: event.operation_status ?? null,
      attempt_number: event.attempt_number ?? null,
      document_page_number: event.document_page_number ?? null,
    });
  }
}

function emptyDoc(): DocumentProgressState {
  return {
    lastEventSequence: 0,
    lastProgressVersion: 0,
    operationId: null,
    operationStatus: null,
    attemptNumber: 1,
    documentPageNumber: null,
    selectedPageIndex: null,
    overallPercent: 0,
    terminal: false,
    latestEvent: null,
  };
}

export function reduceProgressEvent(
  state: ProgressReducerState,
  event: ProgressEventLike,
): ProgressReduceResult {
  const sequence = event.event_sequence ?? 0;
  if (sequence > 0 && sequence < state.lastSessionSequence) {
    warnDev("stale_event_rejected", event);
    return { state, accepted: false, reason: "stale_event_rejected" };
  }

  const documentId = event.document_id;
  if (!documentId) {
    return {
      state: {
        ...state,
        lastSessionSequence: Math.max(state.lastSessionSequence, sequence),
      },
      accepted: true,
    };
  }

  const prev = state.byDocument[documentId] ?? emptyDoc();
  const isHeartbeat =
    event.event === "heartbeat" ||
    event.progress_kind === "heartbeat" ||
    event.operation_status === "heartbeat";

  if (sequence > 0 && sequence < prev.lastEventSequence) {
    warnDev("stale_event_rejected", event);
    return { state, accepted: false, reason: "stale_event_rejected" };
  }

  const version = event.progress_version ?? 0;
  if (!isHeartbeat && version > 0 && version < prev.lastProgressVersion) {
    warnDev("stale_event_rejected", event);
    return { state, accepted: false, reason: "stale_event_rejected" };
  }

  if (prev.terminal && event.operation_status && !TERMINAL_STATUSES.has(event.operation_status)) {
    if (DOCUMENT_TERMINAL_EVENTS.has(event.event ?? "") === false) {
      // Reject terminal → active regression for the same document.
      const activeAgain =
        event.operation_status === "started" ||
        event.operation_status === "queued" ||
        event.operation_status === "running";
      if (activeAgain && (event.attempt_number ?? 1) <= prev.attemptNumber) {
        warnDev("invalid_lifecycle_transition", event);
        return { state, accepted: false, reason: "invalid_lifecycle_transition" };
      }
    }
  }

  if (
    event.attempt_number != null &&
    event.attempt_number < prev.attemptNumber &&
    event.operation_id != null &&
    prev.operationId != null &&
    event.operation_id !== prev.operationId
  ) {
    warnDev("stale_event_rejected", event);
    return { state, accepted: false, reason: "stale_event_rejected" };
  }

  if (
    event.document_page_number != null &&
    prev.documentPageNumber != null &&
    event.document_page_number < prev.documentPageNumber &&
    (event.attempt_number ?? prev.attemptNumber) <= prev.attemptNumber &&
    !isHeartbeat
  ) {
    // Older page must not overwrite current page under the same attempt.
    warnDev("stale_event_rejected", event);
    return { state, accepted: false, reason: "stale_event_rejected" };
  }

  if (
    isHeartbeat &&
    version > 0 &&
    version < prev.lastProgressVersion &&
    sequence <= prev.lastEventSequence
  ) {
    warnDev("stale_event_rejected", event);
    return { state, accepted: false, reason: "stale_event_rejected" };
  }

  if (
    event.operation_id != null &&
    prev.operationId === event.operation_id &&
    prev.operationStatus != null &&
    TERMINAL_STATUSES.has(prev.operationStatus) &&
    event.operation_status != null &&
    TERMINAL_STATUSES.has(event.operation_status) &&
    event.operation_status === prev.operationStatus
  ) {
    warnDev("duplicate_event_rejected", event);
    return { state, accepted: false, reason: "duplicate_event_rejected" };
  }

  const nextOverall = Math.max(
    prev.overallPercent,
    Math.min(65, event.overall_percent ?? prev.overallPercent),
  );
  const docTerminal =
    prev.terminal ||
    DOCUMENT_TERMINAL_EVENTS.has(event.event ?? "") ||
    (event.operation_status != null &&
      TERMINAL_STATUSES.has(event.operation_status) &&
      (event.event?.startsWith("document.") ?? false));

  const nextDoc: DocumentProgressState = {
    lastEventSequence: Math.max(prev.lastEventSequence, sequence),
    lastProgressVersion: isHeartbeat
      ? prev.lastProgressVersion
      : Math.max(prev.lastProgressVersion, version),
    operationId: event.operation_id ?? prev.operationId,
    operationStatus: event.operation_status ?? prev.operationStatus,
    attemptNumber: Math.max(prev.attemptNumber, event.attempt_number ?? prev.attemptNumber),
    documentPageNumber: event.document_page_number ?? prev.documentPageNumber,
    selectedPageIndex: event.selected_page_index ?? prev.selectedPageIndex,
    overallPercent: nextOverall,
    terminal: docTerminal,
    latestEvent: event,
  };

  return {
    state: {
      lastSessionSequence: Math.max(state.lastSessionSequence, sequence),
      byDocument: { ...state.byDocument, [documentId]: nextDoc },
    },
    accepted: true,
  };
}

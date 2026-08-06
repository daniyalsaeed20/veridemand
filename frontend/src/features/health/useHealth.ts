import { useQuery } from "@tanstack/react-query";

import type { OcrRuntimeStatus, ReadinessResponse } from "../../contracts";
import { fetchLiveness, fetchReadiness } from "./healthApi";

export const healthQueryKeys = {
  liveness: ["health", "live"] as const,
  readiness: ["health", "ready"] as const,
};

const STARTING_STATES = new Set([
  "not_started",
  "starting",
  "loading_detector",
  "loading_recognizer",
  "warming_up",
]);

function readinessPollIntervalMs(data: ReadinessResponse | undefined): number | false {
  const ocr = data?.ocr_runtime;
  if (data?.status === "ready" && (ocr == null || ocr.ready || ocr.state === "ready")) {
    return false;
  }
  if (ocr != null && STARTING_STATES.has(ocr.state)) {
    return 1000;
  }
  if (ocr?.state === "failed" || ocr?.state === "disabled") {
    return 8000;
  }
  if (data?.status === "not_ready") {
    return 3000;
  }
  return false;
}

export function useLiveness(options?: { pollWhileUnreachable?: boolean }) {
  const pollWhileUnreachable = options?.pollWhileUnreachable ?? false;
  return useQuery({
    queryKey: healthQueryKeys.liveness,
    queryFn: ({ signal }) => fetchLiveness(signal),
    refetchInterval: (query) => {
      if (!pollWhileUnreachable) {
        return false;
      }
      // Keep observing after success so a later backend outage is detected
      // (SSE Offline alone is not /health/live).
      if (query.state.status === "error") {
        return 3000;
      }
      return 5000;
    },
    retry: false,
  });
}

export function useReadiness(options?: { pollWhileNotReady?: boolean }) {
  const pollWhileNotReady = options?.pollWhileNotReady ?? false;
  return useQuery({
    queryKey: healthQueryKeys.readiness,
    queryFn: ({ signal }) => fetchReadiness(signal),
    refetchInterval: (query) => {
      if (!pollWhileNotReady) {
        return false;
      }
      if (query.state.status === "error") {
        return 5000;
      }
      return readinessPollIntervalMs(query.state.data);
    },
    retry: false,
  });
}

export function isOcrStarting(ocr: OcrRuntimeStatus | null | undefined): boolean {
  return ocr != null && STARTING_STATES.has(ocr.state) && !ocr.ready;
}

export function isLivenessTransportFailure(error: unknown): boolean {
  if (!error || typeof error !== "object") {
    return false;
  }
  const code = "code" in error ? String((error as { code?: string }).code ?? "") : "";
  return (
    code === "network_error" || code === "liveness_timeout" || code === "invalid_liveness_response"
  );
}

/** Consecutive genuine transport failures required before showing backend unavailable. */
export const LIVENESS_OUTAGE_STREAK_THRESHOLD = 2;

/** Advance or clear the liveness failure streak after a query settle. */
export function nextLivenessFailureStreak(
  previous: number,
  outcome: { readonly success: boolean; readonly transportFailure: boolean },
): number {
  if (outcome.success) {
    return 0;
  }
  if (outcome.transportFailure) {
    return previous + 1;
  }
  return previous;
}

export function isPersistentLivenessOutage(
  streak: number,
  isError: boolean,
  error: unknown,
): boolean {
  return isError && isLivenessTransportFailure(error) && streak >= LIVENESS_OUTAGE_STREAK_THRESHOLD;
}

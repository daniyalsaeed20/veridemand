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

export function useLiveness() {
  return useQuery({
    queryKey: healthQueryKeys.liveness,
    queryFn: ({ signal }) => fetchLiveness(signal),
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
      return readinessPollIntervalMs(query.state.data);
    },
  });
}

export function isOcrStarting(ocr: OcrRuntimeStatus | null | undefined): boolean {
  return ocr != null && STARTING_STATES.has(ocr.state) && !ocr.ready;
}

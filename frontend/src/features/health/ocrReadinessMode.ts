import type { OcrRuntimeStatus, ReadinessResponse } from "../../contracts";
import { isOcrStarting } from "./useHealth";

export type OcrReadinessPanelMode =
  | "hidden"
  | "starting"
  | "ready_flash"
  | "failed_retryable"
  | "failed_terminal"
  | "disabled"
  | "backend_unreachable"
  | "readiness_unavailable";

export interface OcrPanelModeInput {
  readonly readiness: ReadinessResponse | undefined;
  /** True only when /health/live cannot be reached (network/timeout/invalid). */
  readonly livenessUnreachable: boolean;
  /** Readiness query failed for a non-transport reason (HTTP 500, bad body, timeout). */
  readonly readinessQueryFailed?: boolean;
  readonly readinessErrorCode?: string | null;
}

/**
 * Precedence: backend unreachable → readiness unavailable → OCR failed →
 * OCR starting → ready → disabled → hidden.
 */
export function deriveOcrPanelMode(
  readinessOrInput: ReadinessResponse | undefined | OcrPanelModeInput,
  readinessErrorLegacy?: boolean,
): OcrReadinessPanelMode {
  const input: OcrPanelModeInput =
    readinessOrInput !== null &&
    typeof readinessOrInput === "object" &&
    "livenessUnreachable" in readinessOrInput
      ? readinessOrInput
      : {
          readiness: readinessOrInput as ReadinessResponse | undefined,
          // Legacy signature treated any readiness error as unreachable — callers
          // must migrate to OcrPanelModeInput. Keep safe default for tests that
          // pass (undefined, true) meaning unreachable.
          livenessUnreachable: readinessErrorLegacy === true,
          readinessQueryFailed: false,
        };

  if (input.livenessUnreachable) {
    return "backend_unreachable";
  }

  if (input.readinessQueryFailed) {
    // Timeout while live: treat as still starting/checking, not network outage.
    if (input.readinessErrorCode === "readiness_timeout") {
      return "starting";
    }
    return "readiness_unavailable";
  }

  const readiness = input.readiness;
  const ocr = readiness?.ocr_runtime;
  if (ocr == null) {
    if (readiness?.status === "not_ready") {
      return "starting";
    }
    return "hidden";
  }
  if (ocr.state === "disabled") {
    return "disabled";
  }
  if (ocr.ready || ocr.state === "ready") {
    return "ready_flash";
  }
  if (ocr.state === "failed") {
    return ocr.retryable ? "failed_retryable" : "failed_terminal";
  }
  if (isOcrStarting(ocr as OcrRuntimeStatus)) {
    return "starting";
  }
  return "hidden";
}

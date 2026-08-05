import type { OcrRuntimeStatus, ReadinessResponse } from "../../contracts";
import { isOcrStarting } from "./useHealth";

export type OcrReadinessPanelMode =
  | "hidden"
  | "starting"
  | "ready_flash"
  | "failed_retryable"
  | "failed_terminal"
  | "disabled"
  | "backend_unreachable";

export function deriveOcrPanelMode(
  readiness: ReadinessResponse | undefined,
  readinessError: boolean,
): OcrReadinessPanelMode {
  if (readinessError) {
    return "backend_unreachable";
  }
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

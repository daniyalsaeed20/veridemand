import { sendJson } from "../../api/http";
import type { OcrRetryAcceptedResponse } from "../../contracts";
import { zOcrRetryAcceptedResponse } from "../../contracts";

export function retryOcrRuntime(signal?: AbortSignal): Promise<OcrRetryAcceptedResponse> {
  return sendJson("/api/v1/runtime/ocr/retry", {
    method: "POST",
    schema: zOcrRetryAcceptedResponse,
    signal,
  });
}

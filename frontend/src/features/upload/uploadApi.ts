import { sendJson } from "../../api/http";
import type { UploadBatchResponse } from "../../contracts";
import { zUploadBatchResponse } from "../../contracts";
import { sessionPath } from "../session/sessionApi";

// Uploads can carry large files; give the request a generous ceiling well above
// the small JSON default. There is no fake progress bar — the request simply
// resolves when the server finishes streaming and validating every file.
const UPLOAD_TIMEOUT_MS = 300_000;

export function uploadDocuments(
  sessionId: string,
  files: readonly File[],
  signal?: AbortSignal,
): Promise<UploadBatchResponse> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file, file.name);
  }
  return sendJson(`${sessionPath(sessionId)}/documents`, {
    method: "POST",
    schema: zUploadBatchResponse,
    body: form,
    signal,
    timeoutMs: UPLOAD_TIMEOUT_MS,
  });
}

import { z } from "zod";

import { sendJson } from "../../api/http";
import { sessionPath } from "../session/sessionApi";
import type { DocumentSummary } from "../viewer/viewerApi";
import { zDocumentSummary } from "../viewer/viewerApi";

const zVoid = z.void();

export function cancelDocument(
  sessionId: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<DocumentSummary> {
  return sendJson(`${sessionPath(sessionId)}/documents/${documentId}/cancel`, {
    method: "POST",
    schema: zDocumentSummary,
    signal,
  });
}

export function removeDocument(
  sessionId: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<void> {
  return sendJson(`${sessionPath(sessionId)}/documents/${documentId}`, {
    method: "DELETE",
    schema: zVoid,
    signal,
  });
}

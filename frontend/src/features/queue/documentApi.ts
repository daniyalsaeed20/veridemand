import { z } from "zod";

import { sendJson } from "../../api/http";
import type { DocumentSummary } from "../../contracts";
import { zDocumentSummary } from "../../contracts";
import { sessionPath } from "../session/sessionApi";

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

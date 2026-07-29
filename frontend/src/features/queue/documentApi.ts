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

const zUnknown = z.unknown();

export function moveDocumentAhead(
  sessionId: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<unknown> {
  return sendJson(`${sessionPath(sessionId)}/documents/${documentId}/priority`, {
    method: "POST",
    json: { action: "move_ahead" },
    schema: zUnknown,
    signal,
  });
}

export function moveDocumentBehind(
  sessionId: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<unknown> {
  return sendJson(`${sessionPath(sessionId)}/documents/${documentId}/priority`, {
    method: "POST",
    json: { action: "move_behind" },
    schema: zUnknown,
    signal,
  });
}

export function restoreDocumentPriority(
  sessionId: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<unknown> {
  return sendJson(`${sessionPath(sessionId)}/documents/${documentId}/priority`, {
    method: "POST",
    json: { action: "restore_default_priority" },
    schema: zUnknown,
    signal,
  });
}

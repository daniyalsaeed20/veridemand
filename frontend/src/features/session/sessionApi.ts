import { z } from "zod";

import { getJson, sendJson } from "../../api/http";
import type { ProcessResponse, SessionSnapshot } from "../../contracts";
import { zProcessResponse, zSessionSnapshot } from "../../contracts";

const zVoid = z.void();

export function sessionPath(sessionId: string): string {
  return `/api/v1/sessions/${sessionId}`;
}

export function createSession(signal?: AbortSignal): Promise<SessionSnapshot> {
  return sendJson("/api/v1/sessions", { method: "POST", schema: zSessionSnapshot, signal });
}

export function getSession(sessionId: string, signal?: AbortSignal): Promise<SessionSnapshot> {
  return getJson(sessionPath(sessionId), { schema: zSessionSnapshot, signal });
}

export function deleteSession(sessionId: string, signal?: AbortSignal): Promise<void> {
  return sendJson(sessionPath(sessionId), { method: "DELETE", schema: zVoid, signal });
}

export function processDocuments(
  sessionId: string,
  documentIds: string[] | null,
  signal?: AbortSignal,
): Promise<ProcessResponse> {
  return sendJson(`${sessionPath(sessionId)}/process`, {
    method: "POST",
    schema: zProcessResponse,
    json: { document_ids: documentIds },
    signal,
  });
}

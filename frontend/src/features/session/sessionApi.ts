import { z } from "zod";

import { getJson, sendJson } from "../../api/http";
// Uses the temporary Phase 2 contract overrides from the viewer feature (see
// the comment at the top of `viewerApi.ts`) rather than the stale generated
// `../../contracts` schemas, so a real backend response — which now reports
// `"canonicalising"` and the canonical-view fields — parses successfully
// instead of throwing.
import type { ProcessResponse, SessionSnapshot } from "../viewer/viewerApi";
import { zProcessResponse, zSessionSnapshot } from "../viewer/viewerApi";

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

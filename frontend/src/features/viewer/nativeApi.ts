// Phase 3 native trust-gate API. Native candidates are only exposed for
// accepted pages; the server redacts text for all other decisions.
import {
  zNativeDocumentSummary,
  zNativePageResult,
  type NativeDocumentSummary,
  type NativePageResult,
} from "../../contracts";
import { getJson } from "../../api/http";

function nativeBasePath(sessionId: string, documentId: string): string {
  return `/api/v1/sessions/${sessionId}/documents/${documentId}/native`;
}

export function getNativeSummary(
  sessionId: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<NativeDocumentSummary> {
  return getJson(`${nativeBasePath(sessionId, documentId)}/summary`, {
    schema: zNativeDocumentSummary,
    signal,
  });
}

export function getNativePage(
  sessionId: string,
  documentId: string,
  pageNumber: number,
  signal?: AbortSignal,
): Promise<NativePageResult> {
  return getJson(`${nativeBasePath(sessionId, documentId)}/pages/${pageNumber}?include_characters=false`, {
    schema: zNativePageResult,
    signal,
  });
}

// Phase 4 printed visual OCR API. Results are provisional: handwriting and
// final document structure remain unevaluated.
import {
  zVisualDocumentSummary,
  zVisualPageResult,
  type VisualDocumentSummary,
  type VisualPageResult,
} from "../../contracts";
import { getJson } from "../../api/http";

function visualBasePath(sessionId: string, documentId: string): string {
  return `/api/v1/sessions/${sessionId}/documents/${documentId}/visual`;
}

export function getVisualSummary(
  sessionId: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<VisualDocumentSummary> {
  return getJson(`${visualBasePath(sessionId, documentId)}/summary`, {
    schema: zVisualDocumentSummary,
    signal,
  });
}

export function getVisualPage(
  sessionId: string,
  documentId: string,
  pageNumber: number,
  signal?: AbortSignal,
  options?: {
    readonly includeLines?: boolean;
    readonly includeWords?: boolean;
    readonly includeBlocks?: boolean;
  },
): Promise<VisualPageResult> {
  const params = new URLSearchParams({
    include_lines: String(options?.includeLines ?? true),
    include_words: String(options?.includeWords ?? true),
    include_blocks: String(options?.includeBlocks ?? true),
  });
  return getJson(
    `${visualBasePath(sessionId, documentId)}/pages/${pageNumber}?${params.toString()}`,
    {
      schema: zVisualPageResult,
      signal,
    },
  );
}

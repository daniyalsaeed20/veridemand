// TanStack Query hook for canonical page metadata (Phase 2).
//
// Server state (the canonical metadata itself) belongs in the query cache,
// never in the Zustand viewer store. This intentionally does not poll: the
// session snapshot (via SSE-driven invalidation) is the source of truth for
// *when* a document becomes ready; this hook only fetches the metadata once
// that is true.

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { getCanonicalMetadata, type CanonicalDocumentMetadata } from "./viewerApi";

export const viewerKeys = {
  canonicalMetadata: (sessionId: string, documentId: string) =>
    ["viewer", "canonical-metadata", sessionId, documentId] as const,
  overlayProof: (sessionId: string, documentId: string) =>
    ["viewer", "overlay-proof", sessionId, documentId] as const,
};

export interface UseCanonicalDocumentOptions {
  readonly enabled?: boolean;
}

export function useCanonicalDocument(
  sessionId: string | null,
  documentId: string | null,
  options: UseCanonicalDocumentOptions = {},
): UseQueryResult<CanonicalDocumentMetadata> {
  const enabled = Boolean(sessionId) && Boolean(documentId) && (options.enabled ?? true);
  return useQuery({
    queryKey:
      sessionId && documentId
        ? viewerKeys.canonicalMetadata(sessionId, documentId)
        : ["viewer", "canonical-metadata", "disabled"],
    queryFn: ({ signal }) =>
      getCanonicalMetadata(sessionId as string, documentId as string, signal),
    enabled,
    // Canonical metadata for a ready document is immutable for the lifetime
    // of the runtime session, so there is no need to ever refetch it.
    staleTime: Infinity,
    retry: false,
  });
}

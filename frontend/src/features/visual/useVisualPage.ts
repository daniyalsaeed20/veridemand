import { useQuery } from "@tanstack/react-query";

import { getVisualPage } from "./visualApi";

export function useVisualPage(
  sessionId: string,
  documentId: string | null,
  pageNumber: number,
  enabled: boolean,
) {
  return useQuery({
    queryKey:
      sessionId && documentId
        ? ["viewer", "visual-page", sessionId, documentId, pageNumber]
        : ["viewer", "visual-page", "disabled"],
    queryFn: ({ signal }) =>
      getVisualPage(sessionId, documentId as string, pageNumber, signal, {
        includeLines: true,
        includeWords: true,
        includeBlocks: true,
      }),
    enabled: enabled && Boolean(documentId) && pageNumber >= 1,
    staleTime: Infinity,
    retry: false,
  });
}

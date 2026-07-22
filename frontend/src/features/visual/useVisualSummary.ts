import { useQuery } from "@tanstack/react-query";

import { getVisualSummary } from "./visualApi";

export function useVisualSummary(sessionId: string, documentId: string | null, enabled: boolean) {
  return useQuery({
    queryKey:
      sessionId && documentId
        ? ["viewer", "visual-summary", sessionId, documentId]
        : ["viewer", "visual-summary", "disabled"],
    queryFn: ({ signal }) => getVisualSummary(sessionId, documentId as string, signal),
    enabled: enabled && Boolean(documentId),
    staleTime: Infinity,
    retry: false,
  });
}

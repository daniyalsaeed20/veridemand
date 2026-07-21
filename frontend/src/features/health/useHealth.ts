import { useQuery } from "@tanstack/react-query";

import { fetchLiveness, fetchReadiness } from "./healthApi";

export const healthQueryKeys = {
  liveness: ["health", "live"] as const,
  readiness: ["health", "ready"] as const,
};

export function useLiveness() {
  return useQuery({
    queryKey: healthQueryKeys.liveness,
    queryFn: ({ signal }) => fetchLiveness(signal),
  });
}

export function useReadiness() {
  return useQuery({
    queryKey: healthQueryKeys.readiness,
    queryFn: ({ signal }) => fetchReadiness(signal),
  });
}

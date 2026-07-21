import { QueryClient } from "@tanstack/react-query";

// Backend-derived state lives in TanStack Query. Retries are limited to a
// single transient attempt, focus refetching is disabled, and the cache is
// never persisted (runtime-only product principle).
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: false,
        staleTime: 15_000,
      },
      mutations: {
        retry: 0,
      },
    },
  });
}

export const queryClient = createQueryClient();

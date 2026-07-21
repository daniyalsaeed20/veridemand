// TanStack Query keys for runtime session state (server state lives here, never
// in Zustand).

export const sessionKeys = {
  root: ["session"] as const,
  detail: (sessionId: string) => ["session", sessionId] as const,
};

import { HealthResponseSchema, type HealthResponse } from "../schemas/health";

const baseUrl =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${baseUrl}/api/v1/health`);
  if (!response.ok) {
    throw new Error(`Health request failed (${response.status})`);
  }
  const json: unknown = await response.json();
  const parsed = HealthResponseSchema.safeParse(json);
  if (!parsed.success) {
    throw new Error("Backend health response failed contract validation");
  }
  return parsed.data;
}

export type { HealthResponse };

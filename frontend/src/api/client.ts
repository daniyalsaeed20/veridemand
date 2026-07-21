import { z } from "zod";
import { ErrorEnvelopeSchema } from "../schemas/generated/ErrorEnvelope";
import { HealthResponseSchema, type HealthResponse } from "../schemas/health";

export type ErrorEnvelope = z.infer<typeof ErrorEnvelopeSchema>;

const baseUrl =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly envelope: ErrorEnvelope | null;

  constructor(status: number, message: string, envelope: ErrorEnvelope | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.envelope = envelope;
  }
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const json: unknown = await response.json();
    const parsed = ErrorEnvelopeSchema.safeParse(json);
    if (parsed.success) {
      return new ApiError(response.status, parsed.data.message, parsed.data);
    }
  } catch {
    /* fall through */
  }
  return new ApiError(response.status, `Request failed (${response.status})`);
}

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${baseUrl}/api/v1/health/live`);
  if (!response.ok) {
    throw await parseError(response);
  }
  const json: unknown = await response.json();
  const parsed = HealthResponseSchema.safeParse(json);
  if (!parsed.success) {
    throw new Error("Backend health response failed contract validation");
  }
  return parsed.data;
}

export type { HealthResponse };

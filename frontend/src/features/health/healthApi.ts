import { ApiError, getJson } from "../../api/http";
import { environment } from "../../api/environment";
import type { LivenessResponse, ReadinessResponse } from "../../contracts";
import { zLivenessResponse, zReadinessResponse } from "../../contracts";

export function fetchLiveness(signal?: AbortSignal): Promise<LivenessResponse> {
  return getJson("/health/live", { schema: zLivenessResponse, signal });
}

/**
 * Fetch readiness. ``/health/ready`` returns HTTP 503 with a valid
 * ``ReadinessResponse`` body when required components are not ready; treat that
 * as observational data, not a transport failure.
 */
export async function fetchReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  const url = `${environment.apiBaseUrl}/health/ready`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8_000);
  if (signal) {
    if (signal.aborted) {
      controller.abort();
    } else {
      signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
  } catch (cause) {
    throw new ApiError("The backend could not be reached.", {}, { cause });
  } finally {
    clearTimeout(timeout);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = undefined;
  }

  if (response.ok || response.status === 503) {
    const parsed = zReadinessResponse.safeParse(body);
    if (parsed.success) {
      return parsed.data;
    }
  }

  throw new ApiError("The backend returned an error.", {
    status: response.status,
    requestId: response.headers.get("X-Request-ID") ?? undefined,
  });
}

import { ApiError, getJson } from "../../api/http";
import { environment } from "../../api/environment";
import type { LivenessResponse, ReadinessResponse } from "../../contracts";
import { zLivenessResponse, zReadinessResponse } from "../../contracts";

const LIVENESS_TIMEOUT_MS = 8_000;
/** Must exceed native-worker self-check and first-ready model hashing. */
const READINESS_TIMEOUT_MS = 45_000;

function isAbortError(cause: unknown): boolean {
  return (
    (cause instanceof DOMException && cause.name === "AbortError") ||
    (cause instanceof Error && cause.name === "AbortError")
  );
}

async function fetchJsonWithTimeout(
  path: string,
  timeoutMs: number,
  signal?: AbortSignal,
): Promise<{ response: Response; body: unknown }> {
  const url = `${environment.apiBaseUrl}${path}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  if (signal) {
    if (signal.aborted) {
      controller.abort();
    } else {
      signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }

  try {
    const response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = undefined;
    }
    return { response, body };
  } finally {
    clearTimeout(timeout);
  }
}

export async function fetchLiveness(signal?: AbortSignal): Promise<LivenessResponse> {
  try {
    const { response, body } = await fetchJsonWithTimeout(
      "/health/live",
      LIVENESS_TIMEOUT_MS,
      signal,
    );
    if (response.ok) {
      const parsed = zLivenessResponse.safeParse(body);
      if (parsed.success) {
        return parsed.data;
      }
      throw new ApiError("The backend returned an unusable liveness response.", {
        status: response.status,
        code: "invalid_liveness_response",
        requestId: response.headers.get("X-Request-ID") ?? undefined,
      });
    }
    throw new ApiError("The backend returned an error.", {
      status: response.status,
      code: "http_error",
      requestId: response.headers.get("X-Request-ID") ?? undefined,
    });
  } catch (cause) {
    if (cause instanceof ApiError) {
      throw cause;
    }
    if (isAbortError(cause)) {
      throw new ApiError(
        "Backend liveness check timed out.",
        { code: "liveness_timeout" },
        { cause },
      );
    }
    throw new ApiError("The backend could not be reached.", { code: "network_error" }, { cause });
  }
}

/**
 * Fetch readiness. ``/health/ready`` returns HTTP 503 with a valid
 * ``ReadinessResponse`` body when required components are not ready; treat that
 * as observational data, not a transport failure.
 */
export async function fetchReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  try {
    const { response, body } = await fetchJsonWithTimeout(
      "/health/ready",
      READINESS_TIMEOUT_MS,
      signal,
    );
    if (response.ok || response.status === 503) {
      const parsed = zReadinessResponse.safeParse(body);
      if (parsed.success) {
        return parsed.data;
      }
      throw new ApiError("The backend returned an unusable readiness response.", {
        status: response.status,
        code: "invalid_readiness_response",
        requestId: response.headers.get("X-Request-ID") ?? undefined,
      });
    }
    throw new ApiError("The backend returned an error.", {
      status: response.status,
      code: "http_error",
      requestId: response.headers.get("X-Request-ID") ?? undefined,
    });
  } catch (cause) {
    if (cause instanceof ApiError) {
      throw cause;
    }
    if (isAbortError(cause)) {
      throw new ApiError("Readiness check timed out.", { code: "readiness_timeout" }, { cause });
    }
    throw new ApiError("The backend could not be reached.", { code: "network_error" }, { cause });
  }
}

/** @deprecated Prefer fetchLiveness; kept for call sites that used getJson previously. */
export function fetchLivenessViaGetJson(signal?: AbortSignal): Promise<LivenessResponse> {
  return getJson("/health/live", { schema: zLivenessResponse, signal });
}

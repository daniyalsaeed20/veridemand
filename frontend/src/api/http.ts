// Small, testable fetch helper.
//
// - Resolves requests against the validated API base URL.
// - Enforces an explicit timeout via AbortController.
// - Parses JSON safely and preserves the backend error envelope.
// - Validates successful responses with a caller-supplied Zod schema.
// - Never retries, never uses local storage, never logs response bodies.

import type { ZodType } from "zod";

import { environment } from "./environment";

const DEFAULT_TIMEOUT_MS = 8_000;

export interface ApiErrorInfo {
  readonly status?: number;
  readonly code?: string;
  readonly requestId?: string;
}

export class ApiError extends Error {
  readonly status?: number;
  readonly code?: string;
  readonly requestId?: string;

  constructor(message: string, info: ApiErrorInfo = {}, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "ApiError";
    this.status = info.status;
    this.code = info.code;
    this.requestId = info.requestId;
  }
}

export interface GetJsonOptions<T> {
  readonly schema: ZodType<T>;
  readonly signal?: AbortSignal;
  readonly timeoutMs?: number;
}

function extractErrorEnvelope(body: unknown): { code?: string; message?: string } {
  if (typeof body === "object" && body !== null && "error" in body) {
    const error = (body as { error: unknown }).error;
    if (typeof error === "object" && error !== null) {
      const detail = error as { code?: unknown; message?: unknown };
      return {
        code: typeof detail.code === "string" ? detail.code : undefined,
        message: typeof detail.message === "string" ? detail.message : undefined,
      };
    }
  }
  return {};
}

export async function getJson<T>(path: string, options: GetJsonOptions<T>): Promise<T> {
  const { schema, timeoutMs = DEFAULT_TIMEOUT_MS } = options;
  const url = `${environment.apiBaseUrl}${path}`;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  if (options.signal) {
    if (options.signal.aborted) {
      controller.abort();
    } else {
      options.signal.addEventListener("abort", () => controller.abort(), { once: true });
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

  const requestId = response.headers.get("X-Request-ID") ?? undefined;

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = undefined;
  }

  if (!response.ok) {
    const envelope = extractErrorEnvelope(body);
    throw new ApiError(envelope.message ?? "The backend returned an error.", {
      status: response.status,
      code: envelope.code,
      requestId,
    });
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError(
      "The backend response did not match the expected contract.",
      { status: response.status, requestId },
      { cause: parsed.error },
    );
  }

  return parsed.data;
}

export interface SendJsonOptions<T> {
  readonly method: "POST" | "DELETE";
  readonly schema: ZodType<T>;
  readonly json?: unknown;
  readonly body?: BodyInit;
  readonly signal?: AbortSignal;
  readonly timeoutMs?: number;
}

// POST/DELETE helper mirroring getJson's error handling and Zod validation.
// `json` sends a JSON body; `body` (e.g. FormData) is sent as-is so the browser
// can set the multipart boundary. Never retries and never uses storage.
export async function sendJson<T>(path: string, options: SendJsonOptions<T>): Promise<T> {
  const { method, schema, json, body, timeoutMs = DEFAULT_TIMEOUT_MS } = options;
  const url = `${environment.apiBaseUrl}${path}`;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  if (options.signal) {
    if (options.signal.aborted) {
      controller.abort();
    } else {
      options.signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }

  const headers: Record<string, string> = { Accept: "application/json" };
  let requestBody: BodyInit | undefined = body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    requestBody = JSON.stringify(json);
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: requestBody,
      signal: controller.signal,
    });
  } catch (cause) {
    throw new ApiError("The backend could not be reached.", {}, { cause });
  } finally {
    clearTimeout(timeout);
  }

  const requestId = response.headers.get("X-Request-ID") ?? undefined;

  let responseBody: unknown;
  try {
    responseBody = await response.json();
  } catch {
    responseBody = undefined;
  }

  if (!response.ok) {
    const envelope = extractErrorEnvelope(responseBody);
    throw new ApiError(envelope.message ?? "The backend returned an error.", {
      status: response.status,
      code: envelope.code,
      requestId,
    });
  }

  const parsed = schema.safeParse(responseBody);
  if (!parsed.success) {
    throw new ApiError(
      "The backend response did not match the expected contract.",
      { status: response.status, requestId },
      { cause: parsed.error },
    );
  }

  return parsed.data;
}

// Fire-and-forget best-effort DELETE for page unload. Uses keepalive so the
// request can outlive the page; failures are intentionally ignored.
export function deleteBeacon(path: string): void {
  const url = `${environment.apiBaseUrl}${path}`;
  try {
    void fetch(url, { method: "DELETE", keepalive: true }).catch(() => undefined);
  } catch {
    // Ignore: this is a best-effort cleanup on unload.
  }
}

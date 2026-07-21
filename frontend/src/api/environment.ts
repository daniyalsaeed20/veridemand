// Validated, immutable frontend environment.
//
// `VITE_API_BASE_URL` must be a valid http(s) URL. A localhost default is only
// applied in development so that a missing production value fails loudly rather
// than silently pointing at a developer machine.

const DEV_FALLBACK_API_BASE_URL = "http://127.0.0.1:8000";

function resolveApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  const raw =
    configured && configured.length > 0
      ? configured
      : import.meta.env.DEV
        ? DEV_FALLBACK_API_BASE_URL
        : undefined;

  if (!raw) {
    throw new Error(
      "VITE_API_BASE_URL is not set. Provide a valid http(s) URL for the backend API.",
    );
  }

  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error(`VITE_API_BASE_URL is not a valid URL: ${raw}`);
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error(`VITE_API_BASE_URL must use http or https, got: ${parsed.protocol}`);
  }

  // Normalise: drop any trailing slash so path joining is predictable.
  return raw.replace(/\/+$/, "");
}

export interface Environment {
  readonly apiBaseUrl: string;
}

export const environment: Environment = Object.freeze({
  apiBaseUrl: resolveApiBaseUrl(),
});

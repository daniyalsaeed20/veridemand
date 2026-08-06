import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchLiveness, fetchReadiness } from "./healthApi";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const baseReady = {
  status: "not_ready" as const,
  service: "veridemand-api" as const,
  app_name: "VeriDemand",
  version: "0.1.0",
  application_version: "0.1.0",
  git_commit: "abc1234",
  process_id: 1,
  worker_generation: 1,
  configuration_profile: "development+ocr_on",
  timestamp: "2026-07-21T14:53:54.484945Z",
  request_id: "req-test",
  checks: [],
  ocr_runtime: {
    state: "starting" as const,
    ready: false,
    retryable: true,
    stage_count: 5,
    attempt_number: 1,
    detector_status: "pending" as const,
    recognizer_status: "pending" as const,
    model_verification_status: "pending" as const,
  },
};

describe("healthApi transport classification", () => {
  it("treats readiness 503 with valid body as success data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify(baseReady), {
            status: 503,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );
    const data = await fetchReadiness();
    expect(data.status).toBe("not_ready");
    expect(data.ocr_runtime?.state).toBe("starting");
  });

  it("tags readiness timeout distinctly from network_error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise((_resolve, reject) => {
            queueMicrotask(() => reject(new DOMException("Aborted", "AbortError")));
          }),
      ),
    );
    await expect(fetchReadiness()).rejects.toMatchObject({ code: "readiness_timeout" });
  });

  it("tags liveness network failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    await expect(fetchLiveness()).rejects.toMatchObject({ code: "network_error" });
  });

  it("tags readiness HTTP 500 as http_error not network", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "boom" }), {
            status: 500,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );
    await expect(fetchReadiness()).rejects.toMatchObject({
      code: "http_error",
      status: 500,
    });
  });
});

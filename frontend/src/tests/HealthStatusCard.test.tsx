import { ThemeProvider } from "@mui/material";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { theme } from "../app/theme";
import { zLivenessResponse } from "../contracts";
import { HealthStatusCard } from "../features/health/HealthStatusCard";

function renderWithProviders(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ThemeProvider theme={theme}>{ui}</ThemeProvider>
    </QueryClientProvider>,
  );
}

const LIVE_BODY = {
  status: "ok",
  service: "veridemand-api",
  app_name: "VeriDemand",
  version: "0.1.0",
  timestamp: "2026-07-21T14:53:54.484945Z",
  request_id: "req-test-123",
};

const READY_BODY = {
  status: "ready",
  service: "veridemand-api",
  app_name: "VeriDemand",
  version: "0.1.0",
  timestamp: "2026-07-21T14:53:54.484945Z",
  request_id: "req-test-123",
  checks: [
    { name: "settings", status: "pass", required: true, message: null },
    { name: "temp_storage", status: "pass", required: true, message: null },
  ],
};

function jsonResponse(body: unknown, init?: { ok?: boolean; status?: number }): Response {
  return {
    ok: init?.ok ?? true,
    status: init?.status ?? 200,
    headers: { get: (key: string) => (key === "X-Request-ID" ? "req-test-123" : null) },
    json: async () => body,
  } as unknown as Response;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("HealthStatusCard", () => {
  it("renders live, ready, request id and backend URL on success", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) =>
      String(input).endsWith("/health/ready") ? jsonResponse(READY_BODY) : jsonResponse(LIVE_BODY),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<HealthStatusCard />);

    expect(await screen.findByText("Live")).toBeInTheDocument();
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    expect(screen.getAllByText("req-test-123").length).toBeGreaterThan(0);
    expect(screen.getByText("http://127.0.0.1:8000")).toBeInTheDocument();
  });

  it("shows an unavailable state and a manual retry control on failure without leaking errors", async () => {
    const secret = "boom-internal-stacktrace-secret";
    const fetchMock = vi.fn(async () => {
      throw new Error(secret);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<HealthStatusCard />);

    expect((await screen.findAllByText("Unavailable")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /retry health checks/i })).toBeInTheDocument();
    expect(screen.queryByText(secret)).not.toBeInTheDocument();
  });

  it("rejects an invalid health payload with the generated Zod schema", () => {
    const result = zLivenessResponse.safeParse({ status: "ok" });
    expect(result.success).toBe(false);
  });
});

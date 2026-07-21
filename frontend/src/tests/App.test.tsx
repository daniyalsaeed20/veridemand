import { render, screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../app/App";
import { AppProviders } from "../app/AppProviders";
import { useAppShellStore } from "../app/useAppShellStore";
import { RUNTIME_WARNING_TEXT } from "../components/RuntimeWarning";

function stubHealthFetch() {
  const headers = { get: (key: string) => (key === "X-Request-ID" ? "req-test-shell" : null) };
  const live = {
    status: "ok",
    service: "veridemand-api",
    app_name: "VeriDemand",
    version: "0.1.0",
    timestamp: "2026-07-21T14:53:54.484945Z",
    request_id: "req-test-shell",
  };
  const ready = { ...live, status: "ready", checks: [] };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const body = String(input).endsWith("/health/ready") ? ready : live;
      return { ok: true, status: 200, headers, json: async () => body } as unknown as Response;
    }),
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("App shell", () => {
  it("renders the product title, subtitle, runtime warning and Phase 0 status", () => {
    stubHealthFetch();
    render(
      <AppProviders>
        <App />
      </AppProviders>,
    );

    expect(screen.getByRole("heading", { name: "VeriDemand" })).toBeInTheDocument();
    expect(screen.getByText("Document Extraction Platform")).toBeInTheDocument();
    expect(screen.getByText(RUNTIME_WARNING_TEXT)).toBeInTheDocument();
    expect(screen.getByText("Phase 0 - Repository Foundation and Contracts")).toBeInTheDocument();
  });

  it("does not present upload or extraction as operational controls", () => {
    stubHealthFetch();
    render(
      <AppProviders>
        <App />
      </AppProviders>,
    );

    // Later-phase capabilities appear only as "not yet available" entries.
    expect(screen.getByText("Extraction")).toBeInTheDocument();
    expect(screen.getByText("Upload and queue")).toBeInTheDocument();
    expect(screen.getAllByText("Planned for a later phase").length).toBeGreaterThan(0);

    // No functional upload/extraction actions exist.
    expect(screen.queryByRole("button", { name: /upload/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /extract/i })).toBeNull();
  });
});

describe("App shell store", () => {
  it("updates ephemeral state without persisting it", () => {
    act(() => {
      useAppShellStore.setState({ diagnosticsExpanded: false, mobileNavOpen: false });
    });

    act(() => {
      useAppShellStore.getState().toggleDiagnostics();
      useAppShellStore.getState().setMobileNavOpen(true);
    });

    expect(useAppShellStore.getState().diagnosticsExpanded).toBe(true);
    expect(useAppShellStore.getState().mobileNavOpen).toBe(true);

    // Nothing is written to persistent browser storage.
    expect(window.localStorage.length).toBe(0);
    expect(document.cookie).toBe("");
  });
});

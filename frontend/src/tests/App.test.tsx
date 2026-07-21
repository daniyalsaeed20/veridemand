import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../app/App";
import { AppProviders } from "../app/AppProviders";
import { queryClient } from "../app/queryClient";
import { useAppShellStore } from "../app/useAppShellStore";
import { RUNTIME_WARNING_TEXT } from "../components/RuntimeWarning";
import { clearBootstrap } from "../features/session/sessionBootstrap";
import { makeSnapshot, MockEventSource } from "./testUtils";

function stubBackend() {
  const headers = { get: () => null };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      return {
        ok: true,
        status: init?.method === "POST" ? 201 : 200,
        headers,
        json: async () => makeSnapshot(),
      } as unknown as Response;
    }),
  );
  vi.stubGlobal("EventSource", MockEventSource as unknown as typeof EventSource);
}

beforeEach(() => {
  clearBootstrap();
  MockEventSource.reset();
  queryClient.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  clearBootstrap();
});

describe("App shell", () => {
  it("renders the product title and runtime-only warning", async () => {
    stubBackend();
    render(
      <AppProviders>
        <App />
      </AppProviders>,
    );

    expect(screen.getByRole("heading", { name: "VeriDemand" })).toBeInTheDocument();
    expect(screen.getByText(RUNTIME_WARNING_TEXT)).toBeInTheDocument();
  });

  it("bootstraps a session and shows the upload and queue workspace", async () => {
    stubBackend();
    render(
      <AppProviders>
        <App />
      </AppProviders>,
    );

    expect(await screen.findByRole("heading", { name: "Upload documents" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Documents & queue/ })).toBeInTheDocument();
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

    expect(window.localStorage.length).toBe(0);
    expect(document.cookie).toBe("");
  });
});

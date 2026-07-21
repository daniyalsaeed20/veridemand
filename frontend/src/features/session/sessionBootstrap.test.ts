import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeSnapshot } from "../../tests/testUtils";
import { bootstrapSession, clearBootstrap } from "./sessionBootstrap";

function stubCreateSession() {
  const headers = { get: () => null };
  const fetchMock = vi.fn(async () => ({
    ok: true,
    status: 201,
    headers,
    json: async () => makeSnapshot(),
  }));
  vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
  return fetchMock;
}

beforeEach(() => {
  clearBootstrap();
});

afterEach(() => {
  clearBootstrap();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("bootstrapSession", () => {
  it("creates exactly one session across concurrent calls (Strict Mode safe)", async () => {
    const fetchMock = stubCreateSession();

    const [first, second] = await Promise.all([bootstrapSession(), bootstrapSession()]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(first.session_id).toBe(second.session_id);
  });

  it("reuses the cached promise on a later call", async () => {
    const fetchMock = stubCreateSession();

    await bootstrapSession();
    await bootstrapSession();

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("creates a fresh session after clearBootstrap", async () => {
    const fetchMock = stubCreateSession();

    await bootstrapSession();
    clearBootstrap();
    await bootstrapSession();

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("never writes to persistent browser storage", async () => {
    stubCreateSession();
    await bootstrapSession();

    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    expect(document.cookie).toBe("");
  });

  it("allows a retry after a failed creation", async () => {
    const failing = vi.fn(async () => {
      throw new Error("network down");
    });
    vi.stubGlobal("fetch", failing as unknown as typeof fetch);
    await expect(bootstrapSession()).rejects.toBeTruthy();

    const fetchMock = stubCreateSession();
    const session = await bootstrapSession();
    expect(session.session_id).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

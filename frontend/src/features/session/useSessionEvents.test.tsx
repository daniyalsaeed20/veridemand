import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProgressEvent, ProgressEventType } from "../../contracts";
import { createTestQueryClient, MockEventSource } from "../../tests/testUtils";
import { useSessionEvents } from "./useSessionEvents";

const SESSION_ID = "ses_" + "0".repeat(32);

function makeEvent(event: ProgressEventType, sequence = 1): ProgressEvent {
  return {
    event_id: `evt_${String(sequence).padStart(12, "0")}`,
    event_sequence: sequence,
    event,
    session_id: SESSION_ID,
    timestamp: new Date().toISOString(),
  } as ProgressEvent;
}

function setup(onSessionGone = vi.fn()) {
  const client = createTestQueryClient();
  const invalidateSpy = vi.spyOn(client, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const view = renderHook(() => useSessionEvents(SESSION_ID, { onSessionGone }), { wrapper });
  return { ...view, invalidateSpy, onSessionGone };
}

beforeEach(() => {
  MockEventSource.reset();
  vi.stubGlobal("EventSource", MockEventSource as unknown as typeof EventSource);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("useSessionEvents", () => {
  it("opens a connection and reports connected state", async () => {
    const { result } = setup();
    MockEventSource.latest().emitOpen();
    await waitFor(() => expect(result.current.connected).toBe(true));
  });

  it("invalidates the session query on a valid progress event", async () => {
    const { invalidateSpy } = setup();
    MockEventSource.latest().emit("document.uploaded", makeEvent("document.uploaded"));

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["session", SESSION_ID] }),
    );
  });

  it("invalidates immediately on stream.resync_required", async () => {
    const { invalidateSpy } = setup();
    MockEventSource.latest().emit("stream.resync_required", makeEvent("stream.resync_required"));

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["session", SESSION_ID] }),
    );
  });

  it("calls onSessionGone and closes on session.deleted", async () => {
    const { onSessionGone } = setup();
    const source = MockEventSource.latest();
    source.emit("session.deleted", makeEvent("session.deleted"));

    expect(onSessionGone).toHaveBeenCalledTimes(1);
    expect(source.readyState).toBe(2);
  });

  it("ignores malformed event payloads", async () => {
    const { invalidateSpy } = setup();
    MockEventSource.latest().emitRaw("document.uploaded", "{not valid json");
    // Give any (unexpected) debounced work a chance to run.
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it("ignores heartbeats", async () => {
    const { invalidateSpy } = setup();
    MockEventSource.latest().emit("heartbeat", makeEvent("heartbeat"));
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it("closes the connection on unmount", () => {
    const { unmount } = setup();
    const source = MockEventSource.latest();
    unmount();
    expect(source.readyState).toBe(2);
  });
});

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { environment } from "../../api/environment";
import { zProgressEvent, zProgressEventType } from "../viewer/viewerApi";
import { sessionKeys } from "./sessionKeys";

const PROGRESS_EVENT_TYPES = zProgressEventType.options;

// Debounce window for coalescing bursts of progress events into a single
// snapshot refetch. TanStack Query owns the authoritative server state; SSE only
// signals that a refetch is warranted.
const INVALIDATE_DEBOUNCE_MS = 120;

export interface SessionEventsState {
  readonly connected: boolean;
  readonly reconnecting: boolean;
}

export interface UseSessionEventsOptions {
  readonly onSessionGone: () => void;
}

export function useSessionEvents(
  sessionId: string | null,
  options: UseSessionEventsOptions,
): SessionEventsState {
  const queryClient = useQueryClient();
  const { onSessionGone } = options;
  const [connected, setConnected] = useState(false);
  const [everConnected, setEverConnected] = useState(false);

  useEffect(() => {
    if (sessionId === null) {
      return;
    }

    const url = `${environment.apiBaseUrl}/api/v1/sessions/${sessionId}/events`;
    const source = new EventSource(url);
    let invalidateTimer: number | undefined;

    const invalidateNow = () => {
      void queryClient.invalidateQueries({ queryKey: sessionKeys.detail(sessionId) });
    };

    const scheduleInvalidate = () => {
      if (invalidateTimer !== undefined) {
        return;
      }
      invalidateTimer = window.setTimeout(() => {
        invalidateTimer = undefined;
        invalidateNow();
      }, INVALIDATE_DEBOUNCE_MS);
    };

    const handleEvent = (event: MessageEvent<string>) => {
      let payload: unknown;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      const parsed = zProgressEvent.safeParse(payload);
      if (!parsed.success) {
        return;
      }
      const kind = parsed.data.event;
      if (kind === "heartbeat") {
        return;
      }
      if (kind === "session.deleted") {
        source.close();
        setConnected(false);
        onSessionGone();
        return;
      }
      if (kind === "stream.resync_required") {
        invalidateNow();
        return;
      }
      scheduleInvalidate();
    };

    for (const type of PROGRESS_EVENT_TYPES) {
      source.addEventListener(type, handleEvent as EventListener);
    }

    source.onopen = () => {
      setConnected(true);
      setEverConnected(true);
    };
    source.onerror = () => {
      setConnected(false);
    };

    return () => {
      if (invalidateTimer !== undefined) {
        clearTimeout(invalidateTimer);
      }
      source.close();
    };
  }, [sessionId, queryClient, onSessionGone]);

  return { connected, reconnecting: everConnected && !connected };
}

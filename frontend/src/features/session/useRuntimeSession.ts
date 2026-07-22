import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { deleteBeacon } from "../../api/http";
import type { SessionSnapshot } from "../viewer/viewerApi";
import { bootstrapSession, clearBootstrap } from "./sessionBootstrap";
import { deleteSession, getSession, sessionPath } from "./sessionApi";
import { sessionKeys } from "./sessionKeys";

export interface RuntimeSession {
  readonly sessionId: string | null;
  readonly snapshot: SessionSnapshot | undefined;
  readonly isLoading: boolean;
  readonly error: Error | null;
  readonly expired: boolean;
  readonly isResetting: boolean;
  readonly markGone: () => void;
  readonly reset: () => Promise<void>;
}

export function useRuntimeSession(): RuntimeSession {
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [bootstrapError, setBootstrapError] = useState<Error | null>(null);
  const [expired, setExpired] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  // Set synchronously while a reset is in flight so the deliberate deletion of
  // the outgoing session's stream cannot mark the fresh session as gone.
  const resettingRef = useRef(false);

  useEffect(() => {
    let active = true;
    bootstrapSession()
      .then((snapshot) => {
        if (!active) {
          return;
        }
        setSessionId(snapshot.session_id);
        queryClient.setQueryData(sessionKeys.detail(snapshot.session_id), snapshot);
      })
      .catch((error: unknown) => {
        if (active) {
          setBootstrapError(error instanceof Error ? error : new Error("Failed to start session."));
        }
      });
    return () => {
      active = false;
    };
  }, [queryClient]);

  const snapshotQuery = useQuery({
    queryKey: sessionId ? sessionKeys.detail(sessionId) : sessionKeys.root,
    queryFn: ({ signal }) => getSession(sessionId as string, signal),
    enabled: sessionId !== null && !expired,
  });

  useEffect(() => {
    if (sessionId === null) {
      return;
    }
    const handlePageHide = () => {
      deleteBeacon(sessionPath(sessionId));
    };
    window.addEventListener("pagehide", handlePageHide);
    return () => {
      window.removeEventListener("pagehide", handlePageHide);
    };
  }, [sessionId]);

  const markGone = useCallback(() => {
    // Ignore the deleted event for a session we are deliberately replacing.
    if (resettingRef.current) {
      return;
    }
    setExpired(true);
  }, []);

  const reset = useCallback(async () => {
    resettingRef.current = true;
    setIsResetting(true);
    const previous = sessionId;
    // Unmount the outgoing event stream first so its session.deleted event
    // (from the delete below) never reaches the replacement session.
    setSessionId(null);
    setExpired(false);
    queryClient.removeQueries({ queryKey: sessionKeys.root });
    clearBootstrap();
    try {
      if (previous !== null) {
        try {
          await deleteSession(previous);
        } catch {
          // Best-effort: the session may already be gone.
        }
      }
      const snapshot = await bootstrapSession();
      setSessionId(snapshot.session_id);
      queryClient.setQueryData(sessionKeys.detail(snapshot.session_id), snapshot);
    } finally {
      resettingRef.current = false;
      setIsResetting(false);
    }
  }, [queryClient, sessionId]);

  return {
    sessionId,
    snapshot: snapshotQuery.data,
    isLoading: sessionId === null || snapshotQuery.isLoading,
    error: bootstrapError ?? (snapshotQuery.error as Error | null),
    expired,
    isResetting,
    markGone,
    reset,
  };
}

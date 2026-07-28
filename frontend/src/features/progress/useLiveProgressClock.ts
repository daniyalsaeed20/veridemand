import { useEffect, useSyncExternalStore } from "react";

import { liveProgressClockStore } from "./liveProgressClockStore";

/**
 * Subscribe to the shared 1s live-progress ticker.
 * Acquires the ticker while `active` is true; Strict Mode safe via acquire/release.
 * Visibility is owned by the shared store (one listener), not per hook.
 */
export function useLiveProgressClock(active: boolean): number {
  const now = useSyncExternalStore(
    liveProgressClockStore.subscribe,
    liveProgressClockStore.getSnapshot,
    liveProgressClockStore.getSnapshot,
  );

  useEffect(() => {
    if (!active) {
      return;
    }
    liveProgressClockStore.acquire();
    return () => {
      liveProgressClockStore.release();
    };
  }, [active]);

  return now;
}

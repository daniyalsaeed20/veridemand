import { useEffect, useSyncExternalStore } from "react";

import { liveProgressClockStore } from "./liveProgressClockStore";

/**
 * Subscribe to the shared 1s live-progress ticker.
 * Acquires the ticker while `active` is true; Strict Mode safe via acquire/release.
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

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }
    const onVisibility = () => {
      liveProgressClockStore.setHidden(document.visibilityState === "hidden");
    };
    onVisibility();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return now;
}

/** Shared monotonic live-progress clock (one ticker for the app). */

type Listener = () => void;

let nowMs = 0;
let intervalId: ReturnType<typeof setInterval> | null = null;
let activeCount = 0;
let hidden = false;
const listeners = new Set<Listener>();

function readMonotonic(): number {
  if (typeof performance !== "undefined" && typeof performance.now === "function") {
    return performance.now();
  }
  return Date.now();
}

function tick(): void {
  nowMs = readMonotonic();
  for (const listener of listeners) {
    listener();
  }
}

function ensureInterval(): void {
  if (intervalId !== null || activeCount <= 0 || hidden) {
    return;
  }
  nowMs = readMonotonic();
  intervalId = setInterval(tick, 1000);
}

function clearIntervalIfIdle(): void {
  if (intervalId !== null && (activeCount <= 0 || hidden)) {
    clearInterval(intervalId);
    intervalId = null;
  }
}

export const liveProgressClockStore = {
  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },

  getSnapshot(): number {
    return nowMs || readMonotonic();
  },

  /** Server-snapshot receive time in monotonic ms. */
  captureReceivedAt(): number {
    return readMonotonic();
  },

  acquire(): void {
    activeCount += 1;
    ensureInterval();
  },

  release(): void {
    activeCount = Math.max(0, activeCount - 1);
    clearIntervalIfIdle();
  },

  setHidden(next: boolean): void {
    hidden = next;
    if (hidden) {
      clearIntervalIfIdle();
    } else {
      tick();
      ensureInterval();
    }
  },

  /** Test helpers */
  _resetForTests(): void {
    if (intervalId !== null) {
      clearInterval(intervalId);
      intervalId = null;
    }
    activeCount = 0;
    hidden = false;
    listeners.clear();
    nowMs = 0;
  },

  _activeCountForTests(): number {
    return activeCount;
  },

  _hasIntervalForTests(): boolean {
    return intervalId !== null;
  },
};

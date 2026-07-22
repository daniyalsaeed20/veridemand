// Module-scoped bootstrap promise.
//
// React 19 Strict Mode mounts effects twice in development. Caching the create
// call in a module-scoped promise guarantees exactly one session is created per
// page load regardless of double mounting. The promise is held in memory only;
// nothing is written to localStorage, sessionStorage, IndexedDB or cookies.

import type { SessionSnapshot } from "../viewer/viewerApi";
import { createSession } from "./sessionApi";

let bootstrapPromise: Promise<SessionSnapshot> | null = null;

export function bootstrapSession(): Promise<SessionSnapshot> {
  if (bootstrapPromise === null) {
    bootstrapPromise = createSession().catch((error: unknown) => {
      // Allow a later retry if the initial creation failed.
      bootstrapPromise = null;
      throw error;
    });
  }
  return bootstrapPromise;
}

export function clearBootstrap(): void {
  bootstrapPromise = null;
}

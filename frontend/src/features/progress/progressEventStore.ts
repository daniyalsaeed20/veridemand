/** Session-scoped live progress store fed by SSE reducer + snapshot resync. */

import {
  initialProgressReducerState,
  reduceProgressEvent,
  type ProgressEventLike,
  type ProgressReducerState,
} from "./progressEventReducer";

type Listener = () => void;

let state: ProgressReducerState = initialProgressReducerState;
const listeners = new Set<Listener>();

function emit(): void {
  for (const listener of listeners) {
    listener();
  }
}

export const progressEventStore = {
  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },

  getSnapshot(): ProgressReducerState {
    return state;
  },

  applyEvent(event: ProgressEventLike): boolean {
    const result = reduceProgressEvent(state, event);
    if (result.accepted) {
      state = result.state;
      emit();
    }
    return result.accepted;
  },

  /** Authoritative session snapshot resync — never regresses versions. */
  applySnapshotBaseline(documents: readonly ProgressEventLike[]): void {
    let next = state;
    for (const doc of documents) {
      const result = reduceProgressEvent(next, {
        ...doc,
        event: doc.event ?? "session.snapshot",
        event_sequence: Math.max(
          doc.event_sequence ?? 0,
          next.lastSessionSequence,
          next.byDocument[doc.document_id ?? ""]?.lastEventSequence ?? 0,
        ),
        progress_version: Math.max(
          doc.progress_version ?? 0,
          next.byDocument[doc.document_id ?? ""]?.lastProgressVersion ?? 0,
        ),
      });
      if (result.accepted) {
        next = result.state;
      }
    }
    state = next;
    emit();
  },

  reset(): void {
    state = initialProgressReducerState;
    emit();
  },

  _resetForTests(): void {
    state = initialProgressReducerState;
    listeners.clear();
  },
};

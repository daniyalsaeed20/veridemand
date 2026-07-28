# ADR 0031 — SSE sequence, progress version, and replay

## Status

Accepted (Correction 4)

## Context

Clients could apply stale progress and regress UI state after reconnect.

## Decision

Every public progress event carries `event_id`, `event_sequence`,
`progress_version`, and `server_timestamp`. Sequence is session-monotonic;
`progress_version` advances only on authoritative state changes. Heartbeats may
advance sequence without version. Reconnect uses `Last-Event-ID` replay or the
newest snapshot; the frontend reducer rejects lower sequence/version.

## Consequences

Ordering is not inferred from wall-clock timestamps alone.

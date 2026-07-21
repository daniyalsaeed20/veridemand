# ADR 0007 - Live progress via a per-session SSE broker

- Status: Accepted
- Date: 2026-07-22
- Phase: 1

## Context

The browser needs live upload/queue progress without polling and without implying
results that do not exist. The transport must handle reconnection, brief client
lag, and connection limits, and must never leak resources on disconnect.

## Decision

- **Server-Sent Events (SSE)** over `EventSourceResponse` (`sse-starlette`),
  chosen over WebSockets (no bidirectional need) and over polling (wasteful,
  laggy, and — because reads do not renew the TTL — unable to keep a session
  alive anyway).
- **One `EventBroker` per session** with a monotonic sequence counter, stable
  `evt_` event ids, a bounded replay deque, and bounded per-subscriber queues.
- **Strict event contract.** Every event is a validated `ProgressEvent`
  (`progress.py`) with an event-type enum. `ProgressEvent` appears in the OpenAPI
  document via the session snapshot's `recent_events`, so the frontend gets a
  reusable generated Zod schema and validates every event at runtime.
- **Replay and resync.** A reconnecting client sends `Last-Event-ID`; the broker
  replays buffered events after that id when possible, or emits
  `stream.resync_required` (prompting a snapshot refetch) when the client is too
  far behind or the id is unknown/malformed.
- **Backpressure safety.** A slow subscriber that overflows its bounded queue is
  signalled to resync and then closed, rather than growing memory without bound or
  silently dropping events.
- **Connection cap** per session (`MAX_SSE_CONNECTIONS_PER_SESSION`), returning
  `429` with `sse_connection_limit`.
- **No TTL renewal from the stream.** Heartbeat pings and (re)connections do not
  extend the inactivity deadline (see ADR 0004).
- **Deterministic teardown.** On client disconnect the stream generator cancels
  its helper tasks (queue-get / signal-wait) and disconnects the subscriber, so no
  orphan asyncio tasks remain. `session.deleted` is drained to the client before
  the broker closes.

## Consequences

- The frontend receives ordered, contract-validated events with graceful
  reconnection, and can always fall back to the authoritative snapshot on resync.
- The broker is bounded in memory per session and per subscriber, protecting the
  single process from slow or abandoned clients.
- SSE is one-directional; all client actions remain ordinary REST calls, keeping
  the event channel read-only and simple.

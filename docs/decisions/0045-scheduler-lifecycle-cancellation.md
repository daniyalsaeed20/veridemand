# 0045 — Scheduler lifecycle and cancellation

## Status

Accepted

## Context

The scheduler must integrate with FastAPI lifespan and support cancellation in
every document state without orphaning background tasks.

## Decision

The scheduler is created once during lifespan, owns no background tasks itself,
and is closed during shutdown. Cancellation works in ready (drop work units),
checkpointed (drop remaining, retain published), and running (cooperative via
existing cancellation token) states. One document's cancellation never stops the
scheduler or other documents.

## Consequences

Clean shutdown, no orphan tasks, cancellation isolation between documents.

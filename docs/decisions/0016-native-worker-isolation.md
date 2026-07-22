# ADR 0016 — Native worker isolation

## Status

Accepted (Phase 3)

## Context

PDF parsing is untrusted blocking work and must not stall the FastAPI loop.

## Decision

Run each document through a dedicated Python subprocess via
`asyncio.create_subprocess_exec` (no shell). Parent applies timeout, cancellation,
graceful terminate, then kill. Staging is removed after publish or failure.
Rejected candidate text never leaves worker memory onto disk/stdout.

## Consequences

Slightly higher process overhead; safer cancellation and privacy guarantees.

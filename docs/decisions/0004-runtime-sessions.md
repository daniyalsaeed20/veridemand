# ADR 0004 - Runtime-only in-memory sessions

- Status: Accepted
- Date: 2026-07-22
- Phase: 1

## Context

VeriDemand processes sensitive documents. The product is explicitly runtime-only:
uploaded files and any progress must not outlive the browser session, and nothing
should be silently persisted. Phase 1 introduces sessions, uploads, and a queue,
all of which need somewhere to live.

## Decision

- **Sessions are in-memory domain objects** (`RuntimeSession` /
  `RuntimeDocument`) held in an async-locked `SessionRegistry` on `app.state`.
  There is no database, cache, or cross-process store. A server restart or
  browser refresh starts a brand-new session.
- **On-disk storage is temporary and opaque.** Each session owns
  `<TEMP_ROOT>/sessions/<session_id>/{staging,originals,...}`. Files are named by
  opaque `doc_` identifiers; the original filename is metadata only and never used
  as a path. Every destructive operation is guarded by resolved-path containment
  checks.
- **TTL is an inactivity timeout on a monotonic deadline.** Only user-initiated
  mutations (create, upload, process, cancel, remove) refresh the deadline.
  Read-only reads (`GET` snapshot, list/get document) and SSE (re)connections do
  **not** extend it. This is deliberate: the frontend refetches the snapshot on
  every progress event, including the `session.expiring` warning; if reads renewed
  the TTL, a watched tab could never expire, breaking both the cleanup guarantee
  and the expiry UX.
- **Cleanup is guaranteed by three mechanisms:** a periodic TTL sweep, a startup
  sweep that removes directories abandoned by a previous (possibly force-killed)
  process, and a graceful-shutdown teardown of every session. A CI guard
  (`scripts/check_no_residual_sessions.py`) asserts no residual session data
  remains.
- **The frontend keeps state in memory only** — no `localStorage`,
  `sessionStorage`, IndexedDB, or cookies — and creates exactly one session per
  page load via a module-scoped bootstrap promise (React Strict Mode safe).

## Consequences

- Horizontal scaling is out of scope for Phase 1: a single process owns all
  state, and multiple workers are forbidden (see ADR 0006). This is acceptable for
  the prototype and documented as a limitation.
- Because reads do not renew the TTL, long-lived idle tabs will expire; the UI
  surfaces the warning and the ended state explicitly and offers a new session.
- No sensitive data is written to durable stores; abrupt termination leaves at
  most temporary directories, which the next startup sweep removes.

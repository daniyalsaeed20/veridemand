# ADR 0006 - In-memory single-worker processing queue

- Status: Accepted
- Date: 2026-07-22
- Phase: 1

## Context

Queued documents need orderly, cancellable admission into a (future) extraction
pipeline. Phase 1 must provide the queue skeleton and lifecycle without any
extraction, and without introducing heavyweight infrastructure (Celery, Redis, a
broker service, or a database).

## Decision

- **A `JobQueue` Protocol with an `InMemoryJobQueue` implementation** over
  `asyncio.Queue`, plus a protected ordered pending index for stable, 1-based,
  dynamically recomputed positions. Duplicate enqueue of a job is prevented.
- **Exactly one admission worker.** `QUEUE_ADMISSION_WORKERS` is constrained to
  `1`; the coordinator raises if constructed with any other count. Multiple
  workers would create independent, inconsistent registries/queues in this
  single-process design.
- **A `ProcessingCoordinator`** owns the single worker task, FIFO consumption, job
  state transitions, session-state updates, event publication, and graceful
  shutdown. FastAPI `BackgroundTasks` is deliberately not used for the queue; the
  worker lifecycle is bound to the application lifespan.
- **Cooperative cancellation** via `CancellationToken`: queued jobs are cancelled
  immediately; a running job observes the token at safe points and finalises
  itself. Cancelled tokens are skipped rather than processed.
- **A non-extractive `AdmissionProcessor`** (`Phase1AdmissionProcessor`) that only
  verifies runtime ownership and file integrity (original present, size matches),
  honours cancellation, and marks the document `ready_for_extraction`. Progress is
  capped at 5% and never claims results.
- **Graceful shutdown** closes the queue, cancels the active job, and awaits the
  worker so no orphan tasks remain.

A test-only `QUEUE_ADMISSION_TEST_DELAY_SECONDS` (default `0`; must be `0` in
production) inserts a cooperative delay in admission so E2E can deterministically
observe queued/preparing states and cancellation. It performs no work.

## Consequences

- The queue is simple, dependency-free, and easy to reason about, at the cost of
  single-process, single-worker throughput — an accepted prototype limitation,
  clearly documented.
- The `JobQueue` Protocol and `AdmissionProcessor` Protocol leave clean seams for
  a future distributed queue and real extraction, without leaking those concerns
  into Phase 1 code.

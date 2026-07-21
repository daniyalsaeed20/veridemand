# Phase 1 - Implementation report

- Date: 2026-07-22
- Branch: `phase/1-runtime-sessions-upload-queue`
- Base: `phase-0-foundation-v1` (`e4d2b1f`)
- Tag: `phase-1-runtime-sessions-upload-queue-v1` (annotated, created after all gates passed)

## Summary

Phase 1 delivers a runtime-only session workspace, a defensive multi-document
upload pipeline, an in-memory single-worker processing queue with a
non-extractive admission coordinator, live progress over SSE with replay/resync,
and TTL/shutdown cleanup — plus a responsive upload + queue dashboard. **No
extraction of any kind is performed**: `pypdf`/`Pillow`/`oletools`/`defusedxml`
are used only for structural upload validation. The furthest a document advances
is `ready_for_extraction`, which explicitly claims no results
(`result_available: false`, `extraction_performed: false`).

See `docs/architecture/phase-1-runtime-sessions.md` and ADRs 0004-0007.

## New backend packages

| Package | Responsibility |
|---|---|
| `storage/` | `paths.py` (containment-checked per-session tree), `file_store.py` (chunked streaming, SHA-256, atomic `os.replace`, bounded-retry deletion) |
| `sessions/` | `models.py` (`RuntimeSession`/`RuntimeDocument`, monotonic deadline), `registry.py` (async registry + lifecycle), `service.py` (snapshot) |
| `uploads/` | `filename.py`, `signatures.py`, `validators.py`, `word_validation.py`, `service.py` (Section 15 pipeline) |
| `processing/` | `queue.py` (`JobQueue` Protocol + `InMemoryJobQueue`), `cancellation.py`, `admission.py`, `coordinator.py` (single worker) |
| `progress/` | `broker.py` (bounded replay, subscriber queues, resync), `service.py`, `models.py` |
| `cleanup/` | `service.py` + `worker.py` (periodic TTL sweep, startup sweep, shutdown cleanup) |
| `api/v1/endpoints/` | `sessions.py`, `documents.py`, `jobs.py` |

New contracts: `identifiers.py`, `sessions.py`, `documents.py`, `uploads.py`,
`jobs.py`, `progress.py`, `processing.py`, and Section 36 error codes in
`errors.py`.

## API surface (`/api/v1`)

- `POST /sessions`, `GET /sessions/{id}`, `DELETE /sessions/{id}`
- `GET /sessions/{id}/events` (SSE, connection-capped)
- `POST /sessions/{id}/process`
- `POST /sessions/{id}/documents` (upload), `GET .../documents`, `GET .../documents/{doc}`
- `POST .../documents/{doc}/cancel`, `DELETE .../documents/{doc}`
- `GET /sessions/{id}/jobs`, `GET .../jobs/{job}`

Readiness (`GET /health/ready`) adds required checks: session workspace writable,
coordinator running, cleanup worker running, queue accepting work (503 on any
required failure). Future services remain `not_configured`.

## Frontend

Features under `frontend/src/features/{session,upload,queue}`: module-scoped
single-session bootstrap (Strict Mode safe, memory-only), `useSessionEvents`
(native `EventSource`, Zod-validated events, resync/deleted handling, reconnecting
indicator), `UploadPanel` (client pre-checks, `FormData`, per-file outcomes),
`QueueDashboard`/`DocumentCard` (dynamic positions, Process/Cancel/Remove),
reset-with-confirmation and expiration UX. `App.tsx` shell replaced with
`SessionWorkspace`. `pagehide` best-effort `DELETE` with `keepalive`.

## Dependencies

`python-multipart`, `sse-starlette`, `pypdf`, `Pillow`, `oletools`, `defusedxml`
(exact locked versions + licences in `docs/dependencies/`). No new frontend
dependencies. Notable transitive GPL-3.0 (`pcodedmp`, via `oletools`) is recorded
and not imported by application code.

## Configuration

`Settings` and `.env.example` extended with session/upload/SSE/queue values and
validators (cleanup interval < TTL, warning < TTL, DOCX compression ratio >= 1,
`QUEUE_ADMISSION_WORKERS == 1`, chunk-size bounds). Added test-only
`QUEUE_ADMISSION_TEST_DELAY_SECONDS` (default 0; must be 0 in production).

## Contract hashes (SHA-256)

```text
3b8e30c3cb5f6eddba443c40926821b7889be5a3fef0b85aaea3f71f7688b282  docs/contracts/openapi.json
293f55077ce9fb1e3b8f3aea7f05acbbd11e2b102dc82507c4eb81e4b9872e14  frontend/src/contracts/generated/types.gen.ts
366b24112aed10a654fee6edb3b3b8e0890a43b3dff2229a3d04b5495442a39c  frontend/src/contracts/generated/zod.gen.ts
0b6907b8821cf2b8baa686ee0c4f0e2fc28325b60f8137cbbd42cabf4abfb887  frontend/src/contracts/generated/index.ts
```

Determinism proven by `scripts/check_contracts.py` (generate twice, identical
hashes, clean `git diff`).

## Test counts

- Backend (pytest): **122 passed**.
- Frontend (vitest): **46 passed** (9 files).
- E2E (Playwright, Chromium): **8 passed** across two projects:
  - `chromium` (normal backend): application shell, bulk upload + queue → ready,
    partial rejection, client-side rejection, reset, refresh (new session id, no
    storage).
  - `chromium-holds` (admission-hold + short-TTL backend): queue cancellation and
    TTL warning → session ended.

## Residual-data verification

`scripts/check_no_residual_sessions.py` runs a clean app lifecycle against each
temp root (exercising the startup sweep and shutdown cleanup) and asserts no
`sessions/ses_*` directory survives. Wired into `scripts/check_all.py` and the CI
`e2e` job (`if: always()`).

## Notable design decisions

- **Inactivity TTL, reads do not renew it** (ADR 0004). Read-only snapshot/list
  reads and SSE (re)connections do not extend the deadline; only user mutations
  do. This fixed a real bug: because the frontend refetches on the
  `session.expiring` event, touching on read would perpetually reset the timer and
  a watched tab could never expire.
- **Deterministic SSE teardown** (ADR 0007): the stream cancels its helper tasks
  on client disconnect, eliminating "Task was destroyed but it is pending"
  warnings and orphan tasks.
- **Reset race fix**: the outgoing session's stream is torn down before its
  deliberate deletion, and a reset guard ignores that `session.deleted`, so a
  reset can never leave the fresh session showing "Session ended".

## Known limitations

- Single process, single admission worker (ADR 0006); no horizontal scaling.
- No extraction/rendering/OCR/LLM (by design for this phase).
- `starlette.testclient` emits a cosmetic httpx deprecation warning.

## Phase boundary confirmation

No canonicalisation, PDF render, native-text, OCR, layout, LLM, database, Redis,
Celery, or authentication code was added. Phase 2 was not started.

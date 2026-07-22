# ADR 0016 — Native worker isolation

## Status

Accepted (Phase 3); amended Phase 3.1

## Context

PDF parsing is untrusted blocking work and must not stall the FastAPI loop.
Phase 3 initially used `asyncio.create_subprocess_exec`. On Windows, uvicorn
`--reload` and `workers > 1` select `SelectorEventLoop`, which raises
`NotImplementedError` for asyncio subprocess transports. That broke every
native extraction job under `pnpm dev` while LibreOffice (blocking
`subprocess.run` via `to_thread`) and the health worker self-check continued
to work.

## Decision

Run each document through a dedicated Python subprocess
(`python -m backend.app.extraction.native.worker`, no shell). The parent
spawns with `subprocess.Popen` and supervises asynchronously (poll, progress
NDJSON drain, timeout, cancel → terminate → grace → kill). Isolation remains
mandatory: pdfplumber must not run on the API event loop.

Windows uses `CREATE_NEW_PROCESS_GROUP` so terminate/kill can target the
worker; cancellation limitations must not break the successful extraction path.

## Consequences

Slightly higher process overhead; safer cancellation and privacy guarantees.
Works under Windows SelectorEventLoop (`pnpm dev --reload`) and Linux CI.
CI previously masked the Windows failure because Linux supports asyncio
subprocesses and many coordinator unit tests inject a fake native service.

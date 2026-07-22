# ADR 0019 — Page-streaming resource limits

## Status

Accepted (Phase 4)

## Context

Long scanned documents must not hold every rendered page or OCR tensor in
memory. A long-lived OCR worker is required so models are not reloaded per page.

## Decision

- One long-lived OCR worker process (`OcrWorkerManager` + `subprocess.Popen`).
- Sequential page processing (`render_concurrency=1`, `ocr_concurrency=1`).
- RSS monitoring via `psutil`; recycle after configured page count / RSS ceiling.
- Atomic per-page result publish; incomplete pages removed on cancel/failure.
- Staging under `staging/visual/`; published results under `results/visual/`.

## Consequences

Peak memory is bounded by one page render + model weights. Cancellation retains
already-published pages. Residual-session guards reject leftover visual staging
and results without deleting `.models/`.

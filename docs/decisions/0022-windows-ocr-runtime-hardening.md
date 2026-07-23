# ADR 0022 — Windows OCR worker lifecycle, pipes, and MKL-DNN

## Status

Accepted (Phase 4.1)

## Context

Phase 4 printed OCR passed CI, but Windows `pnpm dev` (`uvicorn --reload`) could
appear stuck near ~30% for many minutes. Diagnosis needed absolute local models,
non-blocking pipes/stdin, page timeouts, reload-safe process trees, and a locked
CPU / MKL-DNN setting — without starting Phase 5 scope.

## Decision

1. **Model paths:** Resolve `ocr_model_root` to an absolute path against the
   repository root. Refuse empty detection/recognition directories so PaddleOCR
   cannot download during document processing.
2. **Readiness / process gate:** `/health/ready` stays 503 until the OCR worker
   reports ready; `POST .../process` returns `ocr_worker_not_ready` (503) when
   OCR is enabled and the worker is not ready. The UI disables Process with:
   *Printed OCR is still starting or unavailable. Check runtime readiness.*
3. **Pipes / timeouts:** Dedicated stdout/stderr drain threads, bounded stderr
   ring, stdin writes via a thread executor, page + document + startup timeouts,
   and Windows `taskkill /F /T` process-tree cleanup. Do **not** use
   `CREATE_NEW_PROCESS_GROUP` (it orphans Paddle children under `--reload`).
4. **Reload:** Uvicorn `--reload` runs ASGI lifespan only in the serving child;
   exactly one OCR worker attaches to that process. Verify with
   `scripts/verify_windows_dev_runtime.py`.
5. **MKL-DNN:** Keep `enable_mkldnn=False` on Windows (and force related env
   flags off). Timed matrix via `scripts/diagnose_mkldnn_windows.py` on this
   host (win32) showed all four cells load+infer successfully; false/4-thread
   was competitive (~1.3s load / ~3.6s infer) and matches the Phase 4 Linux CI
   path. Do not loosen recognition thresholds to “fix” hangs.

## Consequences

- Cold model load no longer blocks API accept; Process is gated until ready.
- Operators must bootstrap models before processing (`pnpm models:ocr:bootstrap`).
- Progress captions surface Waiting / Rendering / Recognising / Publishing stages.
- Cap remains **65%**; Phase 5 (handwriting / structure / vision LLM) stays out.

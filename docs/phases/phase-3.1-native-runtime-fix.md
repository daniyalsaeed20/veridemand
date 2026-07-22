# Phase 3.1 — Native extraction runtime correction

**Date:** 2026-07-22  
**Branch:** `fix/phase-3-native-notimplemented-runtime`  
**Base tag (unchanged):** `phase-3-native-extraction-trust-gate-v1` (`9f18a15`)  
**Corrective tag:** `phase-3-native-extraction-trust-gate-v1.1`

## Root cause

On Windows, `pnpm dev` starts uvicorn with `--reload`. Uvicorn then uses
`SelectorEventLoop`, which raises `NotImplementedError` for
`asyncio.create_subprocess_exec`. Every native job failed after successful
canonicalisation. CI on Linux did not reproduce this; coordinator unit tests
often inject a fake native service.

## Fix

`NativeExtractionRunner` now spawns the same worker module via
`subprocess.Popen` and supervises it asynchronously. Isolation is unchanged.
Structured `logger.exception` records error code, component, operation, and
worker exit code without native text.

## Verification

- Synthetic good-native production path under SelectorEventLoop
- `scripts/verify_native_runtime.py`
- Backend / frontend / E2E / `pnpm check`

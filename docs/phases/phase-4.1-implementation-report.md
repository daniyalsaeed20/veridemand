# Phase 4.1 — Windows OCR runtime stall fix

## Scope

Corrective hardening after `phase-4-visual-detection-printed-ocr-v1`. Does **not**
move the v1 tag. Does **not** start Phase 5. Progress cap remains 65%.

Branch: `fix/phase-4-windows-ocr-runtime-stall`  
Baseline tag: `phase-4-visual-detection-printed-ocr-v1` (`2f3c038`)

## Problem

On Windows `pnpm dev`, Process Documents could sit near **~30%** for 11+ minutes
with little useful logging. Coordinator band 20–32% is native; visual starts at
36%. Stalls were consistent with native hang, silent OCR cold-start after native,
`--reload` orphans, blocking stdin, unused page timeouts, and/or relative model
paths allowing hub side-effects.

## Changes

| Wave | Summary |
|------|---------|
| A | Absolute `ocr_model_root`, reject empty model dirs, no processing-time download; process 503 + UI disable |
| B | Pipe drains, stdin off event loop, page/startup/doc timeouts, process-tree kill, pipe-flood regression |
| C | Reload-safe spawn (no `CREATE_NEW_PROCESS_GROUP`); `scripts/verify_windows_dev_runtime.py` |
| D | Lock `enable_mkldnn=False`; `scripts/diagnose_mkldnn_windows.py` |
| E | Privacy-safe stage logs + SSE captions (Waiting / Rendering / Recognising / Publishing) |
| F–G | Tests, verification, CI on final SHA, tag `phase-4-visual-detection-printed-ocr-v1.1` |

## Diagnosis notes

- Models verify offline (`pnpm models:ocr:verify`) succeeded on the Windows host;
  stall was runtime lifecycle / observability, not “models missing”.
- Stage logger: `backend.app.observability.stage_log` (IDs, component, operation,
  elapsed — never OCR text).
- Root-cause class addressed: OCR cold-start / reload orphans / blocking pipes
  after native (UI could remain near 30% without stage captions).

## Verification

- `pnpm models:ocr:verify` — pass
- `pnpm verify:visual-runtime` — pass
- `pnpm test:ocr:integration` — pass
- `uv run python scripts/verify_windows_dev_runtime.py` — pass
- `uv run --group ocr python scripts/diagnose_mkldnn_windows.py` — pass (local)
- CI green: https://github.com/daniyalsaeed20/veridemand/actions/runs/29998909406
  on `02698def87f771494d2e7e0bb5eaff181b9951be` (code complete); this docs commit
  re-runs CI before the annotated tag.

## MKL-DNN matrix (local win32)

| enable_mkldnn | threads | load_s | infer_s |
|---------------|---------|--------|---------|
| false | 1 | 3.9 | 5.3 |
| false | 4 | 1.3 | 3.6 |
| true | 1 | 1.2 | 4.4 |
| true | 4 | 1.2 | 2.7 |

Production lock remains `enable_mkldnn=False` (ADR 0022) for parity with Linux CI
and hang avoidance.

## Exit line

PHASE 4.1 FIX PASSED — READY FOR PHASE 5

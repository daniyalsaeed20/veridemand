# Phase 4.2 — Active OCR request recovery, observability, and progress

## Phase 4.2 Result

Corrective hardening after `phase-4-visual-detection-printed-ocr-v1.1` is
complete: worker-generation ownership, pending-request Futures that resolve on
loss, bounded page retry, three-level progress (cap 65%), descriptive
development logs, SSE/session snapshot fields, and DocumentCard meters.

## Starting Baseline

| Item | Value |
|------|--------|
| Start tag | `phase-4-visual-detection-printed-ocr-v1.1` |
| Peel | `0146e072b7a4e2b8d56b95ffd187a9f01f97d786` |
| Do not move | `phase-4-visual-detection-printed-ocr-v1` (`2f3c038`), `v1.1` |

## Branch and Git State

Branch: `fix/phase-4-active-ocr-request-restart-stall`  
Code-complete CI-green SHA (pre-report): `2534d245172f4060514f0a0ba4e3ec80554daa05`  
Delivery tag (this report commit after its CI): `phase-4-visual-detection-printed-ocr-v1.2`

## Exact Stalled Operation

Pre-fix failure class: opaque `processing_stage` logs with possible mid-job
worker respawn while the parent wait loop never resolved the in-flight page.

Post-fix long indeterminate op on the two-page synthetic fixture:
`paddle_text_detection` (page 2), with privacy-safe heartbeats holding % fixed.

## First Worker Restart Reason

No worker restart occurred on the successful two-document diagnosis run
(generation stayed **1**). Restart reasons are enumerated in
`OcrWorkerManager` (`ocr_worker_restart` / typed `restart_reason`); unit tests
prove Futures resolve when loss is forced.

## Pending Request Root Cause

`OcrWorkerManager` previously waited on NDJSON without a pending-request
registry or generation stamp. Worker loss could leave the parent awaiting a
response that would never arrive. Fix: `ActiveRequest` + `asyncio.Future`,
monotonic `worker_generation`, resolve-on-loss exactly once, ignore stale gens.

## Worker Generation Lifecycle

Spawn stamps `worker_generation`; commands/responses carry it; loss increments
generation on respawn; stale responses dropped; health/heartbeat/stderr state
reset per spawn.

## Page Retry Behaviour

`VisualOcrService` retries at most once (`attempt=2`) after recoverable worker
loss, resubmitting with `skip_page_numbers=list_published_page_numbers(...)`
and removing incomplete `.part` outputs. Cancel / invalid PDF / geometry /
resource-limit / non-recoverable content errors are not retried.

## Coordinator Terminal Guarantee

Visual jobs end in
`visual_processing_complete|partial|failed|cancelled`. Progress snapshot is
monotonic to **65%**; heartbeats do not advance percent; unused stages emit
`skipped` via the progress model.

## Paddle Runtime Configuration

Worker ready logs `reason_code=enable_mkldnn=false`. Warm-up consumes inference
results and schema-validates. CPU threads remain configured
(`ocr_cpu_threads`); recognition thresholds unchanged.

## Reload Versus Non-Reload Findings

`scripts/verify_windows_dev_runtime.py` compares uvicorn with/without
`--reload`, asserts readiness, and with `--with-ocr` requires
`worker_generation>=1`, distinct worker PID, and worker cleanup after shutdown.

## Progress Percentage Model

Canonical overall map 0–65 with major phase + page percent. Example from
manual timeline: overall **38** / phase **12.5%** / page **25%** during
`paddle_text_detection`; terminal overall **65** / phase **100%** / page
**100%**.

## Development Log Format

`DevProgressFormatter` prints UTC ISO-8601 ms + visible key=value fields.
Example (privacy-safe):

```text
2026-07-23T13:03:36.553Z INFO visual_heartbeat event=visual_heartbeat operation=paddle_text_detection operation_status=heartbeat overall_percent=38.8 major_phase=visual_ocr page_percent=25.0 progress_kind=heartbeat worker_generation=1 attempt_number=1
```

No bare `processing_stage`-only lines remain for VeriDemand progress events.

## Manual Processing Timeline

Sanitised JSON: `docs/phases/phase-4.2-manual-timeline.json`  
Fixture: synthetic mixed native/image PDF (two pages). Both documents reached
`visual_processing_complete` at **65%**.

## Last Real Progress Versus Heartbeats

Real progress advances on stage transitions (render → preprocess → detect → …).
Heartbeats during `paddle_text_detection` keep the same overall/phase/page %
and only refresh deadline remaining / elapsed.

## Worker Restart Timeline

Successful diagnosis: **no** restart; `worker_reuse.reused=true` with
generation **1** for doc1 and doc2. Forced-loss unit coverage in
`backend/tests/test_ocr_worker_loss_resolves.py`.

## Frontend Progress Visibility

`DocumentCard` shows overall %, major phase %, page %, current operation,
elapsed/timeout remaining, and worker attempt. Tests cover caption layout and
three-level meters.

## Stall Location Evidence

Layer isolation + timeline: stall class sits in long Paddle detect after native
trust / visual select; not in native alone. Post-fix path completes without
orphan wait.

## Two-Page Manual Verification

Diagnosis via `scripts/diagnose_phase42_stall.py` (OCR enabled, same lifespan
as app): doc1 terminal `visual_processing_complete` @ 65% (~71s).

## Second-Document Worker Reuse

Doc2 processed in the same client/session without app restart: generation
remained **1**, `reused=true`, terminal `visual_processing_complete` @ 65%
(~129s wall).

## Mixed-Document Verification

Fixture is the synthetic mixed native/image PDF; visual OCR selected the
image-backed page path while overall progress stayed ≤65%.

## Timeout and Recovery Behaviour

Parent-owned end-to-end page deadline; heartbeats report
`deadline_remaining_seconds`. Worker loss resolves Futures and allows one
bounded page retry. Coordinator watchdog paths typed to terminal visual
statuses.

## Security and Privacy

Logs/SSE/timeline omit OCR text, native text, filenames/paths, and raw Paddle
payloads. IDs and stage metadata only.

## Contracts

Pydantic SoT extended on `ProgressEvent` / `DocumentSummary`; Zod regenerated.
SHA-256 (this tree):

| Artifact | SHA-256 |
|----------|---------|
| `docs/contracts/openapi.json` | `10d884320edc0d8a28fcce196c7a028170ab3d3a68e4581bd43c74193a409191` |
| `frontend/src/contracts/generated/zod.gen.ts` | `08631d90a21177c3b1a7fcab80fae3908a7505b0e5199db7319b2f657e7e8540` |
| `frontend/src/contracts/generated/types.gen.ts` | `0be40fc04d016ddd883c7bb115e50590f4c0295b3e6e0d95bb838da1afd7501c` |

## Tests

| Suite | Count / result |
|-------|----------------|
| Backend unit (collected) | 263 |
| Frontend unit | 121 passed |
| New/extended | `test_ocr_worker_loss_resolves.py`, `test_progress_observability.py`, DocumentCard progress tests |
| Real Paddle integration | CI job **Real CPU OCR integration** + smoke Phase 4 — success |
| Playwright e2e | CI job **End-to-end tests** — success |

Confirmation: no request Future left unresolved on worker loss (unit + manager
resolve path). No generic-only `processing_stage` progress logs. Progress never
exceeds 65% in coordinator model or manual timeline. No Phase 5 code
(handwriting/ONNX/OpenAI/PP-Structure).

## Commits

```
17d2e5d fix(logging): show privacy-safe OCR stages in development logs
cf53373 fix(ocr): resolve active requests when OCR worker restarts
99caa90 feat(progress): expose deterministic document phase and page progress
9cfad22 docs(test): add Phase 4.2 stall diagnosis timeline and evidence
9a779b8 fix(ci): format contracts and harden reload OCR lifecycle verify
2273dc1 fix(types): satisfy mypy on progress payload and reload verify
2534d24 test(frontend): match DocumentCard progress caption text layout
```

(plus this report / two-doc timeline commit)

## Corrective Tag

`phase-4-visual-detection-printed-ocr-v1.2` (annotated; does not move v1 / v1.1)

## Remote Delivery

Branch pushed; tag pushed as `git push origin phase-4-visual-detection-printed-ocr-v1.2` (not `--tags`).

## GitHub Actions

Code-complete green run on `2534d24`:
https://github.com/daniyalsaeed20/veridemand/actions/runs/30008501095  
(Follow-up CI on the tagged report SHA recorded after watch.)

## Phase Boundary Confirmation

Phase 5 was not started. Native trust and OCR recognition thresholds were not
loosened. Progress cap remains 65%.

PHASE 4.2 FIX PASSED — READY FOR PHASE 5

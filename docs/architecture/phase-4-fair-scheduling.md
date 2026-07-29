# Phase 4 — Fair Document Scheduling (Correction 7)

## Architecture lock

**Chosen scope:** true **page-quantum fair scheduling** with a dedicated heavy OCR consumer.

- Cheap canonical / native / routing / successful targeted-repair work stays outside the heavy scheduler and can run while OCR is busy.
- Heavy work units are full-OCR pages (`SchedulerWorkUnit` / `WorkClass.FULL_OCR_PAGE`).
- One full-OCR page remains indivisible; safe checkpoint is after atomic page publish.
- After route/select, documents admit page units into `FairDocumentScheduler`. The cheap job worker releases so later documents can progress.
- `_heavy_consumer_loop` claims the next work unit, runs `VisualOcrService.process_selected_pages` for that page (quantum-bounded), yields when the quantum is exhausted, and resumes without repeating published pages.
- `VisualOcrService` is split into `route_and_select_heavy_pages` → `process_selected_pages` → `finalize_visual_summary`. Disabled fair mode still composes these into contiguous whole-document processing.

Enums and API shapes live in `backend/app/contracts/scheduling.py`; the runtime scheduler imports them (single source of truth).

## Overview

Correction 7 introduces deterministic page-boundary fair scheduling for the VeriDemand OCR pipeline. The heavy consumer interleaves OCR work across documents so small documents receive timely turns without waiting behind large scanned documents.

## Problem

Before Correction 7, the processing coordinator used strict FIFO document ordering. A 104-page embedded document could occupy the single OCR worker for the entire duration while a 2-page police scan waited. Native-only documents (like the 97-page text-rich document) also had to wait behind OCR work that they did not need.

## Architecture

### Route-aware admission

Documents are classified by their processing needs after routing:

- **Native-only documents** (all pages retained as digital_native) complete without entering the OCR scheduler. A 97-page native document finishes its cheap pipeline immediately.
- **Mixed documents** (e.g., billing with 7 native + 2 OCR pages) complete their native pages cheaply; only the 2 OCR pages enter the scheduler.
- **Full OCR documents** enter the scheduler with all their heavy pages.

### Weighted round-robin

The scheduler uses deterministic weighted round-robin with three priority classes:

| Priority class | Criteria | Scheduling weight |
|---|---|---|
| `interactive_short` | ≤ `SHORT_DOCUMENT_HEAVY_PAGE_THRESHOLD` heavy pages | Highest (processed first) |
| `normal` | 4–20 heavy pages | Middle |
| `large_background` | > 20 heavy pages | Lowest |

Within each class, documents are served in FIFO admission order. No random selection.

### Page quantum

Each document receives a bounded number of page completions per turn:

- `FAIR_OCR_PAGE_QUANTUM` (default: 2) — full OCR pages per turn
- `FAIR_REPAIR_PAGE_QUANTUM` (default: 2) — targeted repair pages per turn

After completing the quantum, the document yields at a safe page checkpoint so another document can process.

### Starvation prevention

Bounded priority aging ensures no document starves:

- Every `SCHEDULER_AGING_INTERVAL_SECONDS` (default: 30s) of waiting, a document's effective priority increases
- `SCHEDULER_MAX_CONSECUTIVE_TURNS` (default: 4) prevents one document from monopolising the worker
- A continuously ready document eventually runs regardless of priority class

### Safe checkpoints

Documents yield only at safe boundaries:

- After a page is fully published (atomic publication complete)
- After terminal page failure or cancellation
- Never during PDF rendering, Paddle detection/recognition, or result reconciliation
- Never while holding a file or session mutation lock

### OCR model preservation

The single OCR worker subprocess remains loaded across document switches. Switching documents does not reload Paddle models. Expected: one model load, one stable worker generation unless a real worker failure occurs.

## Document state machine

```
not_admitted → ready
ready → running
running → checkpointed
checkpointed → ready
running → completed
running → failed
ready/checkpointed/running → cancelling → cancelled
```

Terminal states (cancelled, completed, failed) cannot return to ready.

## Scheduler lifecycle

- Created once during FastAPI application lifespan
- Ready queues available before requests are accepted
- Shutdown stops admission, cancels pending work, awaits cleanup
- No orphan background tasks remain after shutdown

## Configuration

| Setting | Default | Description |
|---|---|---|
| `FAIR_OCR_SCHEDULING_ENABLED` | `true` | Enable fair scheduling |
| `FAIR_OCR_PAGE_QUANTUM` | `2` | Pages per document turn |
| `FAIR_REPAIR_PAGE_QUANTUM` | `2` | Repair pages per turn |
| `SHORT_DOCUMENT_HEAVY_PAGE_THRESHOLD` | `3` | Max heavy pages for interactive_short priority |
| `SCHEDULER_AGING_ENABLED` | `true` | Enable starvation prevention |
| `SCHEDULER_AGING_INTERVAL_SECONDS` | `30` | Seconds between aging steps |
| `SCHEDULER_MAX_CONSECUTIVE_TURNS` | `4` | Max consecutive turns per document |

When disabled, the coordinator processes documents in strict FIFO order (Correction 6 behaviour).

## Privacy

Scheduler logs and events contain only opaque document/session identifiers, turn numbers, priority classes, and work unit counts. No filenames, text, page images, crops, or private paths are logged.

## Phase boundary

This correction does not:
- Start Phase 5
- Add handwriting recognition or an LLM
- Increase OCR worker parallelism (OCR_WORKERS remains 1)
- Change native trust, duplication, glyph, embedded verification, targeted-repair, or OCR-quality policies

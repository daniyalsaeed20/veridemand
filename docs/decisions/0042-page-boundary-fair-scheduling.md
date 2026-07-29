# 0042 — Page-boundary fair scheduling

## Status

Accepted

## Context

FIFO document processing blocks small documents behind long OCR runs. A 2-page
police scan should not wait behind a 104-page scanned document. Intra-page
preemption is unsafe because Paddle inference is not interruptible.

## Decision

Implement fair scheduling at page boundaries only. Documents yield after
completing a bounded page quantum. The OCR model remains loaded across document
switches. No page is preempted during inference.

**Implementation:** after routing, heavy pages are admitted as work units. A
lifespan-owned `_heavy_consumer_loop` claims units, runs
`VisualOcrService.process_selected_pages` for the claimed page(s), checkpoints
after atomic publish, and yields so another ready document can run. Cheap
canonical/native/routing work proceeds on the admission worker while OCR is busy.

## Consequences

Small documents receive timely turns. Total OCR work is unchanged. Scheduler
complexity increases but remains deterministic and testable.

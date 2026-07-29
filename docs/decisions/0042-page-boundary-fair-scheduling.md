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

**Interim implementation (Correction 7 branch):** the live path uses a
document-level fair scheduler overlay (admission, priority, quantum accounting,
cancel/terminal sync) on the Correction 6 single-job OCR hold. Cross-document
OCR worker interleaving at page checkpoints remains the target architecture and
is tracked as a follow-up exit gate.

## Consequences

Small documents receive timely turns. Total OCR work is unchanged. Scheduler
complexity increases but remains deterministic and testable.

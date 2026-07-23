# Phase 4.2 — Active OCR request recovery, observability, and progress

## Scope

Corrective hardening after `phase-4-visual-detection-printed-ocr-v1.1`.
Does **not** move v1 or v1.1. Does **not** start Phase 5. Progress cap remains 65%.

Branch: `fix/phase-4-active-ocr-request-restart-stall`  
Baseline: `phase-4-visual-detection-printed-ocr-v1.1` (`0146e07`)

## Exact stalled operation (pre-fix evidence class)

Manual failure sat on opaque `processing_stage` logs while a second OCR worker
could start mid-job. Code audit showed: no worker generation ownership, no
pending-request Future resolution on loss, unused `skip_page_numbers` resume,
and `basicConfig` hiding structured extras.

Bounded diagnosis (`scripts/diagnose_phase42_stall.py` on
`mixed-native-image.pdf`) after the fix:

- Last long indeterminate op: `paddle_text_detection` (page 2), heartbeats with
  deadline remaining.
- Terminal: `visual_processing_complete` at **65%**, generation **1**, attempt **1**.
- No unexplained worker restart on this run.
- Timeline: `docs/phases/phase-4.2-manual-timeline.json`

## Changes

| Area | Summary |
|------|---------|
| Logging | `DevProgressFormatter` — UTC ISO-8601 ms + visible fields |
| Worker | Generations, `ActiveRequest` Future, resolve-on-loss, e2e page deadline, restart reasons |
| Service | Bounded page retry via `skip_page_numbers` + published page resume |
| Progress | Three-level model + SSE/DocumentSummary fields |
| Frontend | Detailed overall / phase / page / operation / attempt UI |

## Exit evidence

Filled after CI + tag peel on the final SHA.

PHASE 4.2 FIX INCOMPLETE — DO NOT START PHASE 5

# Phase 4 — Progress and OCR UI follow-ups (post exclusive-histogram)

Sanitised findings outside the exclusive final-route histogram fix. Opaque
labels only; no transcripts. Evidence packs:

- `temp/private_acceptance/live_seven_doc_route_accounting_2026-07-30.json`
- `temp/private_acceptance/live_police_ocr_quality_delta_2026-07-30.json`
- [phase-4-live-seven-doc-route-accounting-evidence.md](phase-4-live-seven-doc-route-accounting-evidence.md)

Build identity for the live observation: commit `408f4faa73c74bed4287339461f75ec968771588`,
`configuration_profile=development+ocr_on+fast_pass`, session
`ses_59027acd96054355b8331ef3b6b968ef`.

These items are **not** addressed on `fix/phase-4-exclusive-route-histograms`
beyond shared summary double-count fixes already in that branch.

---

## Progress defects (P1–P4)

### P1 — Document pages completed vs selected OCR completed — FIXED

**Observation (live):** Mid-run UI showed “Document pages completed: 17 of 104”
while 13 selected OCR pages had also completed.

**Resolution (this branch):**
- `VisualDocumentSummary.pages_completed` and `VisualProgress.pages_completed`
  use `final_route_histogram.exclusive_terminal_total()`.
- Coordinator publishes `final_route_histogram` and sets `document.pages_completed`
  from that exclusive terminal total (mid-run provisional + finalize).
- [`ProcessingDetailsCard.tsx`](../../frontend/src/features/progress/ProcessingDetailsCard.tsx)
  displays `pages_completed` (not `native_pages_completed`).
- Selected OCR completed/remaining remain a separate workload line.

**Still separate:** Selected OCR counters are workload diagnostics and may differ
from exclusive document-page completion by design.

### P2 — Invalid current-turn quantum display

**Observation:** “Processing page 14 of this turn · quantum 13/2” with configured
fair page quantum **2**.

**Likely locus:** [`DocumentCard.tsx`](../../frontend/src/features/queue/DocumentCard.tsx)
renders `scheduler_quantum_completed + 1` and
`quantum ${scheduler_quantum_completed}/${scheduler_quantum}`. Terminal snapshot
on the 104-page document had `scheduler_quantum_completed=87` with
`scheduler_quantum=2` — completed accumulates across the document rather than
resetting per turn.

**Out of scope** for exclusive-histogram; needs fair-scheduler / UI turn display
correction.

### P3 — Batch elapsed equals document elapsed

**Observation:** After earlier documents completed, batch elapsed still matched
current-document elapsed (terminal medical: both ≈ 2503.3 s).

**Likely locus:** [`progress_model.py`](../../backend/app/processing/progress_model.py) /
coordinator clock stamping — batch start may be reset or aliased per document.

### P4 — paddle_ocr_pipeline shows 0.0s

**Observation:** UI “paddle ocr pipeline — 0.0s” while enclosing full OCR primary
work took ~30s (page artefacts show large `paddle_pipeline_duration_seconds`,
e.g. police page 1 ≈ 130 s pipeline).

**Likely locus:** Heartbeat / `operation_elapsed_seconds` vs page-result
`paddle_pipeline_duration_seconds` plumbing; terminal snapshots often show
`operation_elapsed_seconds=0.0`.

---

## OCR quality / UI copy (Q1–Q3)

Do **not** change OCR selection policy in the route-accounting branch.

### Q1 — Police live vs Correction 5 acceptance baseline

| | Previous acceptance | Live (page 1) |
|--|---------------------|---------------|
| Selected pass | primary | **fallback** |
| Lines (approx / published) | ~31 | **296** published |
| Words | ~188 | **414** published |
| Mean confidence | ~0.938 | ~0.84 (`average_recognition_score`) |
| Quality | (gate pass) | `low_quality`; fallback used |

Source SHA-256 (opaque live original):
`24b6745acc7056f2326e8b3004ff95937dff36b381a30ecb3834d1e65c24c449`
(410128 bytes). Models: `PP-OCRv5_mobile_det` / `PP-OCRv5_mobile_rec`.
Primary limit 960 / fallback 1600; `page_profile=dense_form`.

**Count semantics:** Published `line_count` / `word_count` are
**post provisional-item filtering** on the selected pass. Quality objects keep
**raw per-pass** counts (page 1 primary 319/410, fallback 394/512; published
296/414). Provisional filtering applied (`provisional_item_counts` non-zero).

Selection reason codes (page 1): `fallback_measured_quality_improvement`.

Reproducibility investigation only — no policy change here.

### Q2 — Selection reason vs user-facing warning

**Contradiction:** `selection_reason_codes` include
`fallback_measured_quality_improvement` (fallback selected), but warning copy
says “Printed OCR quality is low; fallback did not improve the result.”

**Locus:** [`worker.py`](../../backend/app/extraction/visual/worker.py) appends that
message when `selected_quality` is `low_quality` / `insufficient` **or** when
fallback was tried and primary retained with
`fallback_no_measured_improvement`. Low quality alone triggers the misleading
copy even when fallback was chosen and measured as an improvement.

### Q3 — Misleading `handwriting_pending = 0`

**Observation:** `provisional_item_counts.handwriting_pending = 0` while
`handwriting_assessment = pending_phase_5` and handwriting has not been
performed.

**Locus:** Noise/provisional counting vs Phase 5 pending assessment labeling in
UI — zero pending items is not “handwriting complete.”

---

## Suggested later issues

1. Fair-scheduler quantum display / per-turn reset (P2).
2. Batch vs document elapsed clocks (P3).
3. Operation elapsed for `paddle_ocr_pipeline` (P4).
4. OCR warning copy when fallback is selected (Q2).
5. Handwriting pending field UX vs Phase 5 (Q3).
6. Police dense-form reproducibility vs Correction 5 baseline (Q1).

P1 (document pages completed vs exclusive terminals) is closed on the
route-accounting branch.

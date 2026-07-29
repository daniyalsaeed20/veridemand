# Phase 4 — Live seven-document route-accounting evidence

Opaque private labels only. No transcripts, filenames, page images, or
private paths. Captured before session reset from the active Phase 4 v2 live
run.

## Build identity

| Item | Value |
|------|--------|
| Branch (workspace) | `phase/4-final-consolidation-and-release` |
| Workspace HEAD | `408f4faa73c74bed4287339461f75ec968771588` |
| `/health/live` git_commit | `408f4faa73c74bed4287339461f75ec968771588` |
| Build identity match | true |
| process_id | `7264` |
| worker_generation | `1` |
| configuration_profile | `development+ocr_on+fast_pass` |
| Session (opaque) | `ses_59027acd96054355b8331ef3b6b968ef` |

Local sanitised JSON pack (gitignored):
`temp/private_acceptance/live_seven_doc_route_accounting_2026-07-30.json`

Police OCR quality delta (separate):
`temp/private_acceptance/live_police_ocr_quality_delta_2026-07-30.json`
— see also [phase-4-progress-and-ocr-ui-followups.md](phase-4-progress-and-ocr-ui-followups.md).

## Mid-run UI observation (opaque 104-page document)

Operator-observed while selected OCR was still in progress:

| Field | Value |
|-------|--------|
| `document_pages_total` | 104 |
| `native_pages_retained` | 17 |
| `embedded_ocr_verified` | 17 |
| `full_ocr_pages_selected` | 87 |
| Displayed route sum | **121** |
| Overcount vs pages | **17** (= embedded count) |
| `selected_ocr_pages_completed` | 13 |
| `selected_ocr_pages_remaining` | 74 |

Identity: \(17 + 17 + 87 = 121\), \(121 - 104 = 17\).

## Terminal exclusive histogram (same document)

Per-page `page_result_state` from published visual results:

| Terminal route | Count |
|----------------|------:|
| `digital_native` | 0 |
| `embedded_ocr_verified` | 17 |
| `full_visual_ocr` | 87 |
| **Exclusive sum** | **104** |

Overlapping diagnostics on the same summary:

| Diagnostic | Count |
|------------|------:|
| `native_pages_retained` | 17 |
| `embedded_ocr_pages_verified` | 17 |
| `full_ocr_pages_selected` | 87 |
| Diagnostic sum | 121 |

Root cause: embedded-verified pages are added to both `retained_native` and
`embedded_verified` in visual selection; acceptance/UI helpers that treat
`native_pages_retained` as exclusive `digital_native` double-count.

## Final batch exclusive histogram (7 documents)

Measured page total for this exact live corpus is **218**, derived as the sum of
validated per-document page counts (97+9+2+1+104+2+3). The earlier consolidation
baseline figure of **217** referred to an outdated or different corpus-page
mapping and must not be forced onto this run.

| Terminal route | Count |
|----------------|------:|
| `digital_native` | 107 |
| `embedded_ocr_verified` | 17 |
| `embedded_ocr_targeted_repair` | 0 |
| `full_visual_ocr` | 93 |
| `visual_no_text` | 1 |
| `page_failed` | 0 |
| **Exclusive sum** | **218** |

Overlapping diagnostic batch totals (not exclusive): `native_pages_retained` 124;
`embedded_ocr_pages_verified` 17; `full_ocr_pages` / selected 94.

## Progress inconsistencies

**P1 (document pages completed)** is fixed on the exclusive-histogram branch:
`pages_completed` / `VisualProgress.pages_completed` derive from exclusive
terminal route totals via `final_route_histogram`, and the UI no longer prefers
`native_pages_completed` alone.

See [phase-4-progress-and-ocr-ui-followups.md](phase-4-progress-and-ocr-ui-followups.md)
for remaining findings **P2–P4** and **Q1–Q3**. Terminal snapshots confirmed
`batch_elapsed_seconds` equals `document_elapsed_seconds` on completed
documents, and `scheduler_quantum_completed` can exceed configured quantum `2`
on the long full-OCR document (terminal value 87).

Police OCR quality delta and UI contradictions Q1–Q3 are recorded in the same
follow-up document.

## Privacy statement

This document and the referenced JSON packs exclude extracted text, word/line
transcripts, crop/page images, and original filenames. Opaque document IDs and
aggregate metrics only.

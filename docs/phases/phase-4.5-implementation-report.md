# Phase 4.5 implementation report

## Scope

Hybrid page routing, OCR throughput calibrations (fast-pass, batching, workers 1–2),
route-aware ETA, fair scheduling behind a flag, and a reactive frontend live clock.

## Phase boundary

No handwriting classifier, no LLM, no final structure, no persistence, no
demand-letter code. `handwriting_assessment = pending_phase_5`.

## Delivery

- Starting tag: `phase-4-visual-detection-printed-ocr-v1.5` (`296ea63`)
- Branch: `phase/4.5-hybrid-routing-throughput-live-progress`
- Tag target: `phase-4-visual-detection-printed-ocr-v1.6`
- Stash `wip-phase44-throughput`: left untouched (not applied)

## ADRs

0025–0030 (0024 already existed for combined Paddle pipeline events).

## Corrective fix during acceptance

`EventBroker.publish` initially rejected Phase 4.5 progress kwargs (`TypeError`),
matching the failure class that broke Phase 4.4 when the throughput stash was
applied. Broker now filters optional `ProgressEvent` fields via `**extra` so
route/ETA fields publish without aborting processing.

## Private opaque acceptance (measured)

| Label | Pages | Measured routes | Duration | Pass |
|-------|------:|-----------------|----------:|------|
| private_police_scan | 2 | full_visual_ocr ×2 | 46.2 s | yes |
| private_billing_digital | 1 | digital_native ×1 | 2.0 s | yes |
| private_medical_embedded_ocr | 104 | full_visual_ocr ×104 | 2818.7 s | yes |

Medical document: no pages retained native/embedded after trust; full OCR on all
104 pages at ~22.7 s/page average (worker=1, fast-pass primary 960). Evidence in
`tmp/phase45-acceptance/acceptance.local.json` (gitignored).

## Privacy

Route/performance logs and SSE carry no OCR text, native text, filenames, paths,
or recognition samples.

## Fair scheduling

Implemented behind `FAIR_OCR_SCHEDULING_ENABLED` (default false). Not enabled for
private acceptance in this release.

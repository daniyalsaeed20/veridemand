# Phase 4 overview — Visual detection and printed OCR

Phase 4 processes scanned and hybrid PDFs after Phase 2 canonicalisation and
Phase 3 native trust. Overall progress is capped at **65%**. Default printed OCR
uses **PP-OCRv5_mobile** detection and recognition from Settings
([ADR 0023](../decisions/0023-adaptive-ocr-render-mobile-baseline.md)); product
calibration documents may still reference **PP-OCRv6 medium**
([ADR 0018](../decisions/0018-paddleocr-local-inference.md)). `OCR_WORKERS`
defaults to **1** (allowed range 1–2).

This overview follows the consolidated pipeline order (Corrections 1–7). Related
ADRs: [0017](../decisions/0017-pypdfium2-page-rendering.md)–[0046](../decisions/0046-queue-priority-controls.md).
Correction notes:
[Correction 2](../phases/correction-2-duplicate-layer-billing-routing.md),
[Correction 3](../phases/correction-3-text-rich-native-routing.md),
[Correction 4](phase-4-correction-4-report.md) /
[progress events](phase-4-progress-events.md) /
[live time and ETA](phase-4-live-time-and-eta.md),
[Correction 5](phase-4-ocr-quality-gate.md),
[Correction 6](phase-4-targeted-region-repair.md),
[Correction 7](phase-4-fair-scheduling.md).

---

## 1. Canonical PDF source

Every accepted upload is reduced to one session-scoped canonical PDF under
`canonical/<document_id>.pdf` ([ADR 0008](../decisions/0008-canonical-pdf-policy.md)).
Original PDFs are published byte-identically when valid; images and text use
deterministic producers; DOC/DOCX convert through headless LibreOffice
([ADR 0009](../decisions/0009-libreoffice-conversion.md)). Downstream native
trust, hybrid routing, and visual OCR always read this PDF. Viewers load it
with HTTP byte ranges ([ADR 0012](../decisions/0012-pdfjs-blank-pages.md)).

## 2. Phase 3 native trust decision

Native extraction runs in an isolated worker subprocess
([ADR 0016](../decisions/0016-native-worker-isolation.md)). pdfplumber candidates
are scored by the conservative trust policy ([ADR 0014](../decisions/0014-native-trust-policy.md)).
Accepted pages publish `words` / `characters` / `provisional_native_text`.
Rejected or document-escalated pages keep empty accepted fields and may retain
`verification_words` (`recognition_status=rejected`) for Phase 4 embedded
verification ([ADR 0031](../decisions/0031-native-verification-candidates.md)).
Default public API omits verification candidates
(`include_verification_candidates=false`). Progress reaches **35%** at
`native_trust_complete`. See [phase-3-native-extraction.md](phase-3-native-extraction.md).

Correction 2 tightens duplicate-layer Path A/B truthfulness
(`duplication_quality_score`). Correction 3 quarantines isolated unsupported
glyphs without hard-rejecting an otherwise coherent page.

## 3. Quarantined candidate lifecycle

Untrusted native strings never become public authority. Quarantined glyphs and
verification candidates stay diagnostic-only until a later stage either:

- materialises verified public words (embedded OCR authority), or
- suppresses them and escalates to targeted repair / full visual OCR.

Quarantined strings are never logged or published as accepted extraction
([ADR 0032](../decisions/0032-embedded-authority-invariants.md),
[ADR 0040](../decisions/0040-repair-result-reconciliation.md),
Correction 3 glyph quarantine policy `phase4-c3-v1`).

## 4. Hybrid page routing

A deterministic page router selects the least expensive reliable route
([ADR 0025](../decisions/0025-page-level-hybrid-routing.md);
[phase-4.5-hybrid-routing.md](phase-4.5-hybrid-routing.md)):

1. Trusted digital native text  
2. Visually verified embedded OCR  
3. Targeted region repair  
4. Full-page visual OCR (fallback)  
5. `visual_no_text` / typed page failure when appropriate  

Image dominance is a risk signal, not an automatic full-OCR mandate. Phase 3
document escalation remains provisional; Phase 4 may restore individually
trusted suppressed pages. Handwriting assessment stays `pending_phase_5`.

## 5. Verified embedded OCR

When native trust rejects or suppresses a page that still has usable geometry,
Route B reads `words` or else `verification_words` and runs low-DPI visual
agreement (and optional recognition spot checks)
([ADR 0026](../decisions/0026-embedded-ocr-visual-agreement.md)).
`embedded_ocr_verified` requires completed agreement, materialised public
words/lines with validated geometry, and `visual_result_available=true`
([ADR 0032](../decisions/0032-embedded-authority-invariants.md)). Sparse
coverage of visible ink fails a coverage gate and falls through to full OCR
(Correction 1).

## 6. Targeted regional repair

When embedded OCR is mostly trustworthy but a bounded set of regions fails
verification, Correction 6 repairs only those regions
([ADR 0027](../decisions/0027-targeted-region-repair.md) superseded by
[0038](../decisions/0038-targeted-repair-eligibility.md)–[0041](../decisions/0041-repair-to-full-ocr-fallback.md);
[phase-4-targeted-region-repair.md](phase-4-targeted-region-repair.md)):

- **recognition_only** — trusted geometry; crop known boxes  
- **local_detection_and_recognition** — detect+recognise inside the padded crop  

At most one bounded repair attempt per page, with one allowed method
transition. Failure falls back to full visual OCR. Crops live under
`staging/targeted_repair/` and are removed on success, failure, cancellation,
session reset, and shutdown.

## 7. Full visual OCR

Pages selected for full OCR render one-at-a-time via pypdfium2
([ADR 0017](../decisions/0017-pypdfium2-page-rendering.md)) with adaptive
render-source policy ([ADR 0023](../decisions/0023-adaptive-ocr-render-mobile-baseline.md)).
A long-lived PaddleOCR worker runs local printed detection and recognition.
Coordinates map to normalised top-left `[0, 1]` space. Combined pipeline events
are described in [ADR 0024](../decisions/0024-combined-paddle-ocr-pipeline-events.md).
Provisional reading order is geometric only
([ADR 0021](../decisions/0021-provisional-visual-reading-order.md)).

## 8. Dense-form quality gate

Correction 5 builds `PrintedOcrQualityEvidence` and applies a versioned
primary-pass quality gate
([ADR 0034](../decisions/0034-adaptive-primary-fallback-ocr.md)–[0037](../decisions/0037-provisional-ocr-noise-classification.md);
[phase-4-ocr-quality-gate.md](phase-4-ocr-quality-gate.md)). Dense forms may
run a fast primary pass (detector side 960) then exactly one sequential
fallback at 1600. Mean recognition confidence alone never decides usability.
Handwriting-looking regions are labelled `handwriting_candidate_pending_phase_5`.

## 9. Selected OCR pass

`full_ocr_result_selection` compares primary and fallback via
`OcrPassComparison` and keeps the better validated result. Provisional noise
classification and line grouping run on the **selected** pass only. Published
boxes carry `ocr_pass` provenance.

## 10. Page-result reconciliation

Each page finishes as exactly one terminal `page_result_state`
([ADR 0032](../decisions/0032-embedded-authority-invariants.md)):
`digital_native`, `embedded_ocr_verified`, `embedded_ocr_targeted_repair`,
`full_visual_ocr`, `visual_no_text`, or `page_failed`. Targeted repair
reconciles retained vs repaired geometry spatially
([ADR 0040](../decisions/0040-repair-result-reconciliation.md)). Document
policy after Phase 4 derives from final page authorities. Per-page visual JSON
publishes atomically; the frontend fetches pages lazily.

## 11. Progress and ETA

`ProcessingCoordinator` is the sole publisher of public lifecycle SSE
([ADR 0007](../decisions/0007-sse-progress-broker.md),
[ADR 0030](../decisions/0030-operation-attempt-lifecycle-ownership.md),
[ADR 0031](../decisions/0031-sse-sequence-and-replay.md)). Overall progress is
monotonic and capped at **65%**. Heartbeats must not advance overall percent.
Document page indices and selected-work indices are distinct fields
([ADR 0029](../decisions/0029-canonical-vs-selected-page-indices.md)). Backend
and frontend clocks are monotonic and separate from deadline remaining fields
([ADR 0028](../decisions/0028-live-client-progress-clock.md),
[ADR 0032](../decisions/0032-monotonic-backend-frontend-clocks.md),
[ADR 0033](../decisions/0033-separate-deadline-semantics.md),
[ADR 0029](../decisions/0029-runtime-eta-estimation.md) runtime ETA).

## 12. Fair scheduling

Correction 7 admits heavy full-OCR (and repair) page units into a fair
scheduler so small documents receive timely turns
([ADR 0030](../decisions/0030-fair-document-scheduling.md),
[0042](../decisions/0042-page-boundary-fair-scheduling.md)–[0046](../decisions/0046-queue-priority-controls.md);
[phase-4-fair-scheduling.md](phase-4-fair-scheduling.md)). Cheap
canonical/native/routing work stays outside the heavy consumer.
`FAIR_OCR_SCHEDULING_ENABLED` defaults to **true**; disable to retain FIFO.
Deprecated `FAIR_OCR_PAGE_CHUNK_SIZE` migrates to `FAIR_OCR_PAGE_QUANTUM`.
One full-OCR page remains indivisible; yield only after atomic page publish.
The OCR worker stays loaded across document switches (`OCR_WORKERS=1` baseline).

## 13. Cleanup

Session deletion and TTL sweeps remove originals, canonical PDFs, renders,
repair crops, result JSON, and in-memory objects
(`SESSION_TTL_SECONDS` default 7200). Staging cleanup runs on success,
failure, cancellation, reset, and shutdown. Residual session directories are
guarded by `scripts/check_no_residual_sessions.py`. Rendered page images are
not retained by default (`OCR_SAVE_RENDERED_PAGES=false`).

## 14. Phase 5 boundary

Do **not** start Phase 5 until Phase 4 release exit gates are green with
evidence. Phase 5+ work explicitly out of scope here:

- handwriting classification / local HTR  
- vision-LLM transcription  
- final reading order  
- final table / form structure  
- `final_result_available=true`  

Tag target for this consolidation:
`phase-4-visual-detection-printed-ocr-v2`.

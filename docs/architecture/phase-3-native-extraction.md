# Phase 3 — Native PDF extraction and trust gate

## Scope

Phase 3 extracts native PDF characters and words from the Phase 2 canonical PDF,
scores them with a conservative native-only trust policy, and publishes accepted
text only in ``words`` / ``characters`` / ``provisional_native_text``. Rejected
or suppressed pages never expose accepted output; they may retain
``verification_words`` (``recognition_status=rejected``) for Phase 4.5 embedded
OCR verification (SoT §10.5 diagnostic retention; ADR 0031). Default public API
strips ``verification_words``.

**Explicit limitation:** visual agreement with a rendered page is
`not_evaluated_phase_3` / `null`. Phase 3 must not fabricate a visual score.
Image-dominant pages and corrupt layers escalate to visual authority for Phase 4.

## Flow

1. Canonical PDF ready (15%).
2. Worker subprocess inspects structure with pypdf.
3. pdfplumber extracts candidates (characters, words, image XObject geometry).
4. Coordinates map to top-left normalised page space.
5. Unicode / geometry / duplication / token / image metrics.
6. Hard rejection rules, then weighted trust score.
7. Document policy + optional whole-document escalation (moves accepted words into
   ``verification_words`` rather than deleting boxes).
8. Atomic publish under `results/native/<document_id>/` (accepted fields + optional
   verification candidates).
9. Progress reaches 35% (`native_trust_complete`).

## Isolation

`NativeExtractionRunner` uses `asyncio.create_subprocess_exec` with
`python -m backend.app.extraction.native.worker`. Parsing never runs on the
FastAPI event loop. Timeout and cancellation terminate then kill the worker.

## APIs

- `GET .../native/summary`
- `GET .../native/pages/{page_number}?include_characters=false&include_verification_candidates=false`

## Viewer

Inspection panel shows policy, trust, reasons, and optional native word boxes
(`native_pdf_word`) aligned through the Phase 2 overlay transform — accepted
pages only.

## Phase 4 / 4.5 boundary

No OCR or LLM in Phase 3. Phase 4.5 Route B reads ``words`` or else
``verification_words`` for embedded OCR visual/recognition agreement.

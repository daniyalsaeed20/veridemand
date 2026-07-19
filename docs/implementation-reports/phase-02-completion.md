# Phase 2 Completion Report — Canonical Viewer and Native Extraction

**Status date:** 2026-07-19  
**Branch:** `phase-02-viewer-native-extraction`  
**Verdict:** **PASS WITH GAPS**

---

## 1. Starting audited baseline

| Field | Value |
|-------|-------|
| Tag | `phase-01-audited-pass` (created for this phase start) |
| Commit | `5ab566ff7ad63e51ee8a08f2c7b5ebb6bccec093` |
| Prior branch | `phase-01-audit-hardening` |

Phase 2 work started from that commit on branch `phase-02-viewer-native-extraction`.

---

## 2. Requirement IDs implemented

| ID | Implementation |
|----|----------------|
| **FR-UPL-06** | DOCX → canonical PDF via LibreOffice headless (OD-05 A); original DOCX retained under `uploads/`; viewing copy under `derived/` |
| **FR-UPL-07** | Page counts completed for DOCX after convert; thumbnails via pypdfium2 under `thumbnails/{doc_id}/page_N.png` |
| **FR-EXT-01** | pdfplumber native words → `SourceToken` with normalized polygons |
| **FR-EXT-02** | Provisional native usability scoring (`0.1-provisional` knobs in `AppSettings`) |
| **FR-EXT-06** | Native path → shared `SourceToken` / `SourceSpan` contracts; OCR path deferred to Phase 3 |

**Exit gate (matrix):** “Selected native fact opens exact source” — satisfied in Phase 2 via **selecting a native `SourceSpan`** in the Documents viewer (Facts UI is Phase 5+). Highlight overlay uses normalized → screen mapping at the current zoom.

---

## 3. Open decisions resolved

| OD | Resolution |
|----|------------|
| **OD-05** | **Resolved — option A (LibreOffice headless).** Word COM not implemented. Missing tool / timeout / corrupt output → document-level processing error; original DOCX preserved; session continues. CI uses injectable fake converter. |
| **OD-01** | Still open (provisional thresholds). Phase 2 ships scoring with `0.1-provisional` defaults; no claim of calibrated accuracy. |

---

## 4. Architecture and converter decisions

```text
Upload (Phase 1) → POST /process
  → normalize_document
       PDF: original is canonical view (evidence unchanged)
       DOCX: LibreOffice → derived/{doc_id}.pdf
       JPG/PNG/TIFF: Pillow → derived/{doc_id}.pdf (orientation via exif_transpose)
  → thumbnails (pypdfium2)
  → pdfplumber native extract per page
  → score_native_text_usability → PageRoute native|ocr|manual_review
  → group_tokens_into_spans (native only; OCR route sets ocr_status=pending)
  → PDF.js Documents workspace + span highlight
```

- One LibreOffice conversion at a time (process-wide lock).
- App-controlled temp under session `work/`; partial outputs deleted on failure.
- Coordinates: pdfplumber top-left page units → normalized `[0,1]` top-left; invalid geometry rejected (no silent bad highlight).

---

## 5. Dependencies (production)

| Dependency | Version | Purpose | Licence |
|------------|---------|---------|---------|
| pdfplumber | 0.11.7 | Native PDF text/words/coords | MIT |
| pdfminer.six | (transitive via pdfplumber) | PDF parsing | MIT |
| pypdfium2 | 4.30.0 | Page thumbnails (also Phase 3 OCR render) | Apache-2.0 / PDFium |
| pdfjs-dist | 4.10.38 | Frontend PDF viewer + highlights | Apache-2.0 |
| LibreOffice (system) | host install | DOCX→PDF viewing copy | MPL-2.0 |
| pypdf | 5.9.0 (existing) | Page helpers / blank fixtures | BSD |
| Pillow | 11.3.0 (existing) | Image→PDF, EXIF orientation | HPND |

`python-docx` not added in Phase 2 (structured DOCX extraction deferred; viewing uses PDF copy).

---

## 6. APIs added

| Method | Path |
|--------|------|
| POST | `/api/v1/sessions/{id}/process` |
| GET | `/api/v1/sessions/{id}/events?after=` |
| GET | `/api/v1/sessions/{id}/documents/{doc}/pages` |
| GET | `/api/v1/sessions/{id}/documents/{doc}/pages/{n}` |
| GET | `/api/v1/sessions/{id}/documents/{doc}/view` |
| GET | `/api/v1/sessions/{id}/documents/{doc}/thumbnails/{n}` |
| GET | `/api/v1/sessions/{id}/documents/{doc}/pages/{n}/tokens` |
| GET | `/api/v1/sessions/{id}/documents/{doc}/pages/{n}/spans` |

Session isolation: cross-session / deleted / expired access denied; opaque IDs only; paths never in JSON.

---

## 7. Automated test evidence

`node scripts/check-all.mjs` — **passed** (2026-07-19):

- Backend: ruff format/check, mypy strict, **108 pytest** tests
- Contracts: generate + drift check + drift-proof
- Frontend: prettier, eslint, tsc, vitest (9), production build

Coverage includes: PDF/DOCX/image/TIFF normalize; DOCX success/timeout/failure + partial cleanup; thumbnails; native words/coords; coordinate normalize + multi-zoom highlight math; rotation/cropbox open; multi-column span split; empty/broken routing without OCR; cross-session and post-delete/expiry denial; process events; FE schema + build.

---

## 8. Local reference-package manual acceptance

**Location:** gitignored binaries under `docs/example/` (not committed).

Manual acceptance on the lawyer Amini package should record (aliases/hashes only — **no patient text** in reports):

| Alias (illustrative) | Expect |
|----------------------|--------|
| eCW medical export | Strong native; viewer + highlights |
| Police report | Often OCR-routed; Phase 2 flags `ocr`/`pending` |
| Insurer letter | Mixed / OCR-leaning |
| eCW billing | Broken native → OCR route |
| Long scanned medical | Mostly OCR-routed |
| Firm DOCX | LibreOffice convert → view PDF + thumbs |

**This report does not embed measured timings or confidential filenames.** Operators should fill local notes when running against `docs/example/`. Automated CI does not require those binaries.

---

## 9. Coordinate / highlight evidence

- Unit tests: `tests/unit/test_coordinates.py`, `test_native_extraction.py` (normalized quads; screen rect scales 2× with render size).
- UI: span selection draws overlay at `normalized × rendered_page_size`.

---

## 10. Performance

Not claimed as product SLA. Synthetic integration runs complete in seconds on developer hardware. Page-open latency for large Amini stacks should be noted during local manual acceptance (matrix: document page open latency).

---

## 11. Pages routed toward Phase 3 OCR

Phase 2 sets `PageRoute.ocr` + `ocr_status=pending` (and quality flag `awaiting_ocr`) when provisional heuristics fail. **PaddleOCR is not invoked.** Blank pages may route `manual_review`.

---

## 12. Known limitations / gaps

1. Exit gate exercised via **SourceSpan** selection, not Fact entities (Facts = Phase 5+).
2. LibreOffice required for real DOCX demos; CI uses fake converter.
3. Provisional OCR thresholds (OD-01) — not calibrated; fail-open to OCR route.
4. Module 03 “every page extracted or Issue” is a **Phases 2–3** gate — Phase 2 alone does not claim Module 03 exit.
5. `DocumentPage` contract lacks dedicated rotation/thumbnail/char-count fields; rotation stored server-side; thumbs served by API; token/span counts used.
6. Handwritten / scan pages correctly lack native spans until Phase 3.
7. PDF.js worker chunk is large in production build (warning only).

---

## 13. Deferred work

- Phase 3: pypdfium2 OCR render, PaddleOCR, OpenCV retry, FR-EXT-03..07, quality dashboard
- Classification, facts, chronology, billing, issues, demand, export
- Structured python-docx extraction for DOCX originals

---

## 14. Specification conflicts (recorded, not silently rewritten)

| Tension | Handling |
|---------|----------|
| Module 02 header “Phase 1” vs matrix UPL-06/07 Phase 2 | Follow acceptance matrix + OD-05 |
| Module 03 full exit vs Phase 2 exit | Phase 2 exit only; Module 03 completes with Phase 3 |
| Matrix “native fact” vs no Facts UI yet | Span selection in viewer |

---

## 15. Final verdict

**PASS WITH GAPS**

Phase 2 deliverables (viewer, thumbnails, pdfplumber native tokens/spans, click-to-highlight, FR-UPL-06/07, FR-EXT-01/02/06 native path) are implemented with automated evidence. Gaps are documented (DOCX needs LibreOffice for manual demo; exit gate via spans not facts; provisional thresholds; OCR not executed). Do **not** create `phase-02-audited-pass` until an independent audit. Do **not** begin Phase 3 until that audit and exit review.

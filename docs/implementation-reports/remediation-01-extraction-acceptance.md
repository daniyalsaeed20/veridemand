# Remediation Part 1 — Extraction Acceptance Corpus

**Branch:** `remediation-01-extraction-acceptance`  
**Starting branch / commit:** `phase-05-gold-validation` / `b52943638bc7726436da5e1fb9ee18ba334754ba`  
**Phase 5 implementation commit (unchanged):** `cab86da303ae4340729d56a68194b92c90c4dab1`  
**Date:** 2026-07-20  

**Verdict:** `CORPUS PREPARED — HUMAN GROUND-TRUTH REVIEW PENDING`

---

## Purpose

Define how extraction quality is measured **before** any OCR engine, extraction library, routing rule, parser, or production contract change. Part 1 ships the benchmark, tooling, synthetic fixtures, and acceptance criteria only.

---

## Requirements defined

Committed under `docs/remediation/`:

- Extraction acceptance contract (provenance, hierarchy, geometry, reading order, layer separation, safe failure, hard invariants)
- Evaluation metrics catalogue (text, order, geometry, layers, critical fields, safe failure)
- Acceptance matrix with provisional document-class bands (**proposals** — OD-17)
- Requirements traceability map (code / tests / evidence / gaps / measurement)

Vendor-neutral evaluation schema:

- `docs/remediation/schemas/extraction-result-eval.schema.json`
- Labelled: **EVALUATION SCHEMA — NOT YET PRODUCTION CONTRACT**

---

## Metric catalogue (implemented in tooling)

Text: CER, WER, exact-line match, word precision/recall, spurious/missing token rates, single-char fragment rate, nonsense-token diagnostics, duplicate-layer rate  

Order: line/word agreement, pairwise order error, cross-column/row merges, header/footer merges, table-cell ordering, label/value association  

Geometry: valid/OOB polygon rates, centre-in-region, IoU, rotation correctness  

Layers: corrupt-embed false accept, native false reject, unnecessary OCR, OCR miss, selection accuracy, silent mix  

Critical fields: exact-match scoring (extraction fidelity only)  

Safe failure: outcome accuracy, unsafe-usable count, review-required coverage  

---

## Synthetic fixtures

| Count | Location |
|------:|----------|
| **17** | `fixtures/extraction_acceptance/` |

Covers clean native, two-column, table, label/value, header/footer, rotated, skewed, image-only, correct hidden OCR, **corrupt hidden OCR**, boxed characters, mixed print/hand-like, diagram labels, duplicate hidden text, person name, law-firm name, date/identifier. Ground truth committed with each fixture. **No private case values.**

---

## Private real corpus (gitignored)

| Item | Safe count |
|------|------------:|
| Private real documents present | **9** |
| Selected real pages | **25** |
| Document families / aliases covered | police, insurer, ecw_medical, ecw_billing, long_medical, existing_demand, demand_ahmed, demand_morris, demand_fuentes |

Private locations (do not commit):

- Corpus manifest: `tmp/extraction-remediation/acceptance-corpus/`
- Review pack: `tmp/extraction-remediation/acceptance-review/`
- Baseline: `tmp/extraction-remediation/baseline/`
- Intake (missing badge file note): `tmp/extraction-remediation/intake/`

### Document-class coverage (availability)

Present: clean native narrative, medical, billing/ledger-like, insurer, police family, demand/DOCX-derived families, low-text police page.  

Gaps called out: dedicated TIFF input, firm template binary, dedicated rotated/skewed real page set, **difficult badge police report (9065 / Go6s) not located** (OD-19).

---

## Annotation status

| Status | Notes |
|--------|--------|
| Human-approved gold pages | **0** |
| Machine prefill / unreviewed | All selected pages |
| Prefill label | `UNVERIFIED MACHINE PREFILL` |

Corpus is **not** gold.

---

## Known-anchor coverage

| Anchor | Status |
|--------|--------|
| Client person name (user-confirmed) | Seeded as `USER_CONFIRMED_ANCHOR` on relevant review templates; page link confirmation pending human review |
| Law-firm name (user-confirmed) | Seeded likewise; human page link pending |
| Difficult police badge/ID | **Source file not located** — intake README documents gap; no fabricated annotations |

---

## Baseline measurement status

Generated against current production stack (read-only):

- Native: pdfplumber via existing `extract_native_page`
- Routing: current `PageRoute` decisions recorded
- OCR: forensic/cached tokens preferred; live PaddleOCR only when OCR-routed and cache missing
- Safe aggregates only in this report

Observed route mix on selected pages (counts only): native majority; OCR-routed minority; some aliases skipped (DOCX / unavailable PDF for native probe).

Visible limitation catalogue recorded privately (no repairs): line-level OCR geometry, no character geometry, no table/column model, corrupt-embed risk, Phase 5 facts paused, parser `Patient` substring is **not** an extraction error.

---

## Tooling / tests

| Area | Location |
|------|----------|
| Tooling | `scripts/extraction_acceptance/` |
| Unit tests | `backend/tests/unit/test_extraction_acceptance.py` |
| Automated tests | **23 passed** |

---

## Repository safety

| Check | Result |
|-------|--------|
| Real PDFs / DOCX untracked | Pass |
| Private remediation outputs under `tmp/` ignored | Pass |
| Committed report free of confidential values / hashes / excerpts | Pass |
| Synthetic fixtures free of real case names/values | Pass |
| No API keys / cloud OCR credentials added | Pass |
| Production extraction / OCR / contracts unchanged | Pass |

---

## No-production-change confirmation

- No edits to `backend/app/services/extraction/` or `backend/app/services/ocr/`
- No `SourceToken` / `SourceSpan` contract changes
- No routing changes
- No parser repairs
- No Phase 5 fact regeneration
- No OCR engine selection / upgrade
- No GPT or cloud OCR integration
- Phase 6 not started
- No audited-pass tag created

---

## Open user decisions

- **OD-17** — Approve or revise provisional accuracy bands  
- **OD-18** — Whether character/symbol geometry becomes a firm capability  
- **OD-19** — Provide difficult police intake file for badge/ID layer-selection proof  

---

## Part 1 exit checklist

- [x] Acceptance contract  
- [x] Metrics implemented  
- [x] Vendor-neutral eval schema  
- [x] Safe synthetic fixtures  
- [x] Private corpus manifest  
- [x] Representative pages selected  
- [x] Known anchors represented where files available  
- [x] Annotation/review tooling  
- [x] Baseline measurements generated  
- [x] Private files ignored  
- [x] Safe report (this document)  
- [x] No production extraction code changed  
- [x] No premature OCR engine decision  

**Human ground-truth review remains required** before any page set is called gold and before numeric matrix rows move from `not_evaluated`.

---

## Stop

Remediation Part 2 must not start from this report alone. Extraction measurement infrastructure is ready; engine changes are not authorized yet.

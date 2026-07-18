# Phase Acceptance Matrix

**Status date:** 2026-07-19  
**Crosswalk:** [`docs/modules/README.md`](../modules/README.md) (Phase ≠ Module number).  
**Doctrine:** Do not claim a phase complete without the listed evidence. Honest gold exits require `firm_approved` keys ([`gold-readiness.md`](./gold-readiness.md)).

---

## Phase 0 — Repository and Contracts

| Field | Content |
|-------|---------|
| **Deliverable** | Monorepo scaffold; Pydantic + generated Zod from contracts; AppSettings; health; test harness; dependency/licence inventory |
| **FR IDs** | Architectural: §6.2, §7.1–7.3, §14.1, Appendix D (Module 00 mapping) |
| **Automated evidence** | Schema compile; Pydantic↔Zod health fixture parity; `pytest` one-command green; CI |
| **Manual evidence** | Hit `GET /api/v1/health` in browser/curl |
| **Reference fixture** | Synthetic health JSON; register `docs/example/` metadata only (no OCR) |
| **Perf/quality** | N/A beyond boot |
| **Exit gate** | Schemas compile; FE/BE exchange validated health; tests run with one command |
| **Blocking limitations** | Generator package confirmation (OD-02) soft. |
| **Nonblocking** | TipTap, OCR, LLM absent by design |

---

## Phase 1 — Temporary Session and Upload

| Field | Content |
|-------|---------|
| **Deliverable** | Session manager; upload UI; validation; temp lifecycle; document list |
| **FR IDs** | FR-SES-01..05; FR-UPL-01..05 (UPL-06 soft if converter missing) |
| **Automated evidence** | Upload valid/invalid types; SHA duplicate; session delete cleans files; TTL cleanup callable |
| **Manual evidence** | Upload reference PDFs/DOCX; Reset/Delete; refresh warning visible |
| **Reference fixture** | Amini package under `docs/example/` |
| **Perf/quality** | Enforce size/page limits from AppSettings |
| **Exit gate** | Reference files upload and cleanup verified; no OCR/AI |
| **Blocking** | Scheduler choice (OD-04) |
| **Nonblocking** | DOCX→PDF converter missing → explicit error (OD-05) |

---

## Phase 2 — Canonical Viewer and Native Extraction

| Field | Content |
|-------|---------|
| **Deliverable** | PDF.js viewer; thumbnails; pdfplumber tokens/spans; click-to-highlight |
| **FR IDs** | FR-UPL-06..07; FR-EXT-01..02, FR-EXT-06 (native path) |
| **Automated evidence** | Native word/span normalize `[0,1]`; highlight geometry unit tests |
| **Manual evidence** | Click a native fact → correct page region |
| **Reference fixture** | eCW medical (strong native); police/insurer (native layers exist on sample) |
| **Perf/quality** | Page open latency documented |
| **Exit gate** | Selected native fact opens exact source location where native text exists |
| **Blocking** | None for Phase 0 prior |
| **Nonblocking** | Broken native layers (billing ledger) flagged for Phase 3 OCR |

---

## Phase 3 — OCR Fallback and Page Quality

| Field | Content |
|-------|---------|
| **Deliverable** | pypdfium2; PaddleOCR adapter; OpenCV retry; quality dashboard; hardware bench |
| **FR IDs** | FR-EXT-03..07 |
| **Automated evidence** | Route native/ocr/manual; tokens+confidence+polygons; low-conf critical → Issue not verified fact |
| **Manual evidence** | Overlays on police/insurer/long medical; quality warnings visible |
| **Reference fixture** | EG90156; Dairyland/Patriot letter; long medical stack; eCW billing (broken native) |
| **Perf/quality** | ms/page, peak RAM, route mix — fill `03-ocr-thresholds` measured table |
| **Exit gate** | All reference pages extracted **or** explicitly flagged; baselines documented |
| **Blocking** | Working PaddleOCR runtime on target OS (see OCR spike oneDNN failure) |
| **Nonblocking** | Provisional thresholds until calibrated (OD-01) |

---

## Phase 4 — Document Classification and Sequence

| Field | Content |
|-------|---------|
| **Deliverable** | Taxonomy; rules engine; optional LLM fallback; sequence UI |
| **FR IDs** | FR-CLS-01..06 |
| **Automated evidence** | Rule labels on reference filenames/headings; FR-CLS-06 demand not evidence by default |
| **Manual evidence** | Drag-reorder; correct a mislabel without reprocess |
| **Reference fixture** | Full Amini package + demand DOCX as non-evidence |
| **Perf/quality** | Classification in seconds |
| **Exit gate** | Reference docs classified or corrected quickly without reprocessing |
| **Blocking** | None critical |
| **Nonblocking** | LLM fallback off; thresholds unmeasured (OD-06) |

---

## Phase 5 — Deterministic Facts and Evidence

| Field | Content |
|-------|---------|
| **Deliverable** | DET parsers; fact browser; source nav; Amber/Red gaps; no LLM extraction |
| **FR IDs** | FR-DET-01..06 |
| **Automated evidence** | Must-find present+span **or** queued; silent invent tests fail |
| **Manual evidence** | Open fact → highlight; resolve queue item |
| **Reference fixture** | Amini evidence PDFs; illustrative gold shape; **firm_approved gold for honest exit** |
| **Perf/quality** | Silent critical-error rate = 0 on gold |
| **Exit gate** | Critical exact facts present/traceable or queued; no silent inventing |
| **Blocking** | **Firm-approved gold** for honest claim (OD-07) |
| **Nonblocking** | Demos with illustrative gold if labeled illustrative |

---

## Phase 6 — Timeline, Billing, Optional Semantic Consolidation

| Field | Content |
|-------|---------|
| **Deliverable** | Timeline; billing ledger; Decimal reconciliation; optional Module 11 off by default |
| **FR IDs** | FR-CHR-01..03; FR-BIL-01..04; FR-AI-* optional |
| **Automated evidence** | Arithmetic fixtures; specials confirmation required when undetermined |
| **Manual evidence** | Timeline/billing UI; confirm specials |
| **Reference fixture** | eCW ledger + medical stack; firm gold totals |
| **Perf/quality** | Billing reconciliation accuracy vs gold |
| **Exit gate** | Chronology/billing match gold **or** Issues; LLM skippable |
| **Blocking** | Firm gold chronology/billing; layout rules for broken native ledgers |
| **Nonblocking** | Module 11 disabled |

---

## Phase 7 — Issue Engine and Human Review

| Field | Content |
|-------|---------|
| **Deliverable** | Exact issue rules; G/A/R queue; side-by-side; manual rectangle; decision log |
| **FR IDs** | FR-ISS-01..03,05 (04 optional); FR-REV-01..07 |
| **Automated evidence** | Seeded DOL/fracture/insurer/placeholder issues fire; locked facts immutable |
| **Manual evidence** | Resolve conflict; dependent outputs refresh without full OCR |
| **Reference fixture** | Amini planted defects; draft-defect DOCX set |
| **Perf/quality** | Contradiction recall on seeded set |
| **Exit gate** | Known sample contradictions detected and resolvable; downstream updates |
| **Blocking** | Firm confirmation of expected issues (OD-07/13) |
| **Nonblocking** | Semantic LLM issues optional |

---

## Phase 8 — Demand Generation

| Field | Content |
|-------|---------|
| **Deliverable** | Template manager; structured sections; **docxtpl export first**; paragraph-fact map |
| **FR IDs** | FR-DRF-01..06 |
| **Automated evidence** | Every case-specific paragraph has `supporting_fact_ids`; no raw PDF prompt |
| **Manual evidence** | DOCX opens in Word; sections present |
| **Reference fixture** | Jackman-derived template (spike); approved dummy facts |
| **Perf/quality** | Unsupported factual sentence rate on draft |
| **Exit gate** | Complete demand without raw-document prompting; editable DOCX opens |
| **Blocking** | OD-09 assembly choice for narrative quality |
| **Nonblocking** | TipTap polish deferred |

---

## Phase 9 — Verification and Export

| Field | Content |
|-------|---------|
| **Deliverable** | Preflight; statement support matrix; export blockers; hardened docxtpl |
| **FR IDs** | FR-VAL-01..04; FR-EXP-01..02 |
| **Automated evidence** | Seeded TBD/flags/math block final export; draft export labeled |
| **Manual evidence** | Attorney confirm signal; clean DOCX after resolution |
| **Reference fixture** | Amini demand defects; Ahmed/Morris/Fuentes hygiene DOCX |
| **Perf/quality** | Export blocker precision on fixtures |
| **Exit gate** | Blocks seeded defects; exports clean DOCX after resolution |
| **Blocking** | Attorney confirmation workflow (OD-10) |
| **Nonblocking** | PDF preview / LibreOffice optional |

---

## Phase 10 — Evaluation Demonstration

| Field | Content |
|-------|---------|
| **Deliverable** | Gold runner; metrics; timing; blind-review packet; demo script (Module 12) |
| **FR IDs** | §17 metrics; acceptance table §17.5 |
| **Automated evidence** | Repeatable metric JSON from firm gold |
| **Manual evidence** | Blind review vs current ChatGPT/Claude workflow |
| **Reference fixture** | **Firm-approved** gold (not illustrative alone) |
| **Perf/quality** | Full §17.3 metric set |
| **Exit gate** | Results repeatable; show where prototype is faster/more traceable/less error-prone |
| **Blocking** | Firm gold + baseline timings missing today |
| **Nonblocking** | Illustrative corpus for dry-run of runner only |

---

## Readiness spike evidence (pre-Phase 0)

| Spike | Informs phase | Status |
|-------|---------------|--------|
| OCR | 3 | Measured native routing; PaddleOCR runtime failure on this Windows/oneDNN stack — see `ocr-spike-report.md` |
| Billing | 6 | Native money/codes partial; broken text layer → review/OCR — see `billing-spike-report.md` |
| DOCX | 8 | docxtpl dummy multi-section DOCX generated — see `docx-template-spike-report.md` |

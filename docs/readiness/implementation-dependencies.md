# Implementation Dependencies (Pre-Implementation Readiness)

**Status date:** 2026-07-19  
**Purpose:** Map external dependencies and readiness prerequisites to phases. Spikes under `spikes/` are disposable until reviewed; they are **not** production architecture.

---

## 1. Specification / corpus prerequisites

| Dependency | Purpose | Needed by | Status (this workspace) |
|------------|---------|-----------|-------------------------|
| `docs/prototype_documentation.md` | Doctrine | All phases | Present |
| `docs/contracts/` | Machine field SoT | Phase 0+ | Present (`contracts_version` 0.1) |
| `docs/modules/` | Module design | Phase 0+ | Present (design) |
| `docs/example/*.pdf|docx` | Reference fixtures | Spikes; Phases 1–10 tests | Present locally |
| `docs/example/gold/` | Eval key **shape** | Phase 0 harness; Phase 5–10 | Illustrative only |
| Firm-approved gold (outside public tree) | Honest Phase 5–7/10 exits | Before claiming those exits | **Missing** |

**Path caveat:** Amini demand file on disk is `Demand Mayel  Amini Final.docx` (double space). Fixture loaders must use the real name.

---

## 2. Selected stack (from prototype §6.2) — production intent

| Component | Package / tool | Purpose | Licence (verify at install) | First phase |
|-----------|----------------|---------|-----------------------------|-------------|
| Frontend | React + Vite + TypeScript | UI | MIT (typical) | 0 |
| State | Zustand | Client session state | MIT | 0–1 |
| Validation (FE) | Zod (generated preferred) | API response validation | MIT | 0 |
| Viewer | PDF.js | Page render / highlights | Apache-2.0 | 2 |
| Editor (secondary) | TipTap | Post-docxtpl polish | MIT | 8+ |
| Backend | FastAPI | API | MIT | 0 |
| Schemas | Pydantic v2 | Machine contracts | MIT | 0 |
| Native PDF text | pdfplumber (+ pypdf) | Words/coords | MIT | 2 |
| PDF render | **pypdfium2** | OCR page images | Apache-2.0 / PDFium | 3 (spike now) |
| Image prep | Pillow + OpenCV | Retry preprocess | HPND / Apache-2.0 | 3 |
| OCR | **PaddleOCR** (EN lightweight) | Scanned text | Apache-2.0 | 3 (spike now) |
| DOCX IO | python-docx | Read/write DOCX | MIT | 2 / 8 |
| DOCX template | **docxtpl** | Demand populate | MIT | 8 (spike now) |
| PDF preview (optional) | LibreOffice headless | DOCX→PDF preview / view copy | MPL-2.0 | 1–2 / 9 |
| LLM (optional) | Provider API TBD | Classification / draft / verify | Provider ToS | 4+ optional |

**Prototype constraint:** No paid document-AI services as default extractor.

---

## 3. Spike-only dependencies (isolated under `spikes/`)

| Spike | Packages | Purpose | Promote to app? |
|-------|----------|---------|-----------------|
| `spikes/ocr/` | pypdfium2, paddleocr, paddlepaddle, pdfplumber, Pillow, opencv-python-headless, psutil | Feasibility / thresholds | Only after review + Phase 3 design |
| `spikes/billing/` | pdfplumber, (stdlib Decimal) | Ledger row grouping | Only after review + Phase 6 |
| `spikes/docx-template/` | docxtpl, python-docx | Template fidelity | Only after review + Phase 8 |

Local Python used for readiness: `.tools/python312/` (developer tool install; not part of product).

---

## 4. Phase dependency graph (blocking)

```text
Phase 0  Contracts + health + harness
   └─► Phase 1  Session + upload  (needs OD-04 scheduler; OD-05 converter soft)
         └─► Phase 2  Viewer + native extract
               └─► Phase 3  OCR  (needs PaddleOCR + pypdfium2; OD-01 calibrate)
                     └─► Phase 4  Classification
                           └─► Phase 5  DET facts  ← honest exit needs firm gold (OD-07)
                                 └─► Phase 6  Timeline/billing  ← firm gold + billing layout rules
                                       └─► Phase 7  Issues/review  ← firm gold contradictions
                                             └─► Phase 8  Demand (docxtpl)  (OD-09)
                                                   └─► Phase 9  Preflight/export  (OD-10)
                                                         └─► Phase 10 Eval  ← firm gold + metrics
```

Module 11 (semantic consolidation) remains **optional** and off the critical path.

---

## 5. Hardware / ops (from prototype §16)

| Constraint | Implication |
|------------|-------------|
| 16 GB RAM, single OCR worker | One active OCR job; pause OCR during heavy export if needed |
| Long scanned stacks (~60+ pages) | Multi-minute jobs expected; progress UI required (Phase 3+) |
| GPU optional | CPU-first recommended (OD-15) |

---

## 6. Lawyer / firm dependencies (non-code)

| Item | Blocks honest exit for |
|------|------------------------|
| Verify critical exact facts in evidence (not demand alone) | Phase 5, 10 |
| Chronology / provider ranges | Phase 6, 10 |
| Billing totals / specials confirmation policy | Phase 6, 10 |
| Confirm planted contradictions are expected issues | Phase 7, 10 |
| Attorney-judgment fields remain user-supplied | Phases 5–10 (must-not-invent) |
| Issue severity / waiver policy preferences | Phase 7–9, 10 |

---

## 7. Schema generation tooling (confirmation still required)

Recommended chain is documented in [`contract-generation.md`](./contract-generation.md). Tool versions must be recorded with purpose + licence when added as **production** dependencies (Cursor rule).

| Candidate | Role | Confirm by |
|-----------|------|------------|
| Pydantic v2 `model_json_schema()` | Export JSON Schema | Phase 0 |
| `json-schema-to-zod` or equivalent | Generate Zod | Phase 0 |
| FastAPI OpenAPI export | Optional alternate FE source | Phase 0 if chosen |

---

## 8. Privacy / repo hygiene

- Do not log document text (`log_document_text` default false).  
- Do not send `docs/example/` binaries to public remotes or default LLM pipelines.  
- Spike `out/` directories should remain local / gitignored.

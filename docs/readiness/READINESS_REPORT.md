# Pre-Implementation Readiness Report

**Date:** 2026-07-19  
**Canonical doctrine:** [`docs/prototype_documentation.md`](../prototype_documentation.md)  
**Contracts SoT:** [`docs/contracts/`](../contracts/)  
**Scope:** Readiness closure only — **Phase 0 application implementation was not started.**

---

## Verdict

# READY WITH BLOCKERS LISTED

Phase 0 may begin. Later phases have documented blockers (especially firm-approved gold and a pinned Windows OCR stack for Phase 3 production). Failures and gaps are not hidden.

---

## Supporting findings

### Documentation / decisions

| Artifact | Result |
|----------|--------|
| [`open-decisions.md`](./open-decisions.md) | 15 open decisions catalogued with options, recommendations, phase impact |
| [`spec-conflicts.md`](./spec-conflicts.md) | Documented friction points; hierarchy confirmed (contracts win on shapes) |
| [`implementation-dependencies.md`](./implementation-dependencies.md) | Stack, corpus, lawyer, and spike dependencies mapped |

No silent doctrine expansion. Genuine ambiguities recorded (OD-01…OD-15).

### Gold readiness

| Artifact | Result |
|----------|--------|
| [`gold-readiness.md`](./gold-readiness.md) | Illustrative Amini gold is **not** `firm_approved` |

**Blocks honest exit claims for Phases 5, 6, 7, and 10** until lawyer-verified gold exists. Phase 0–4 harness shape is usable.

### Spikes (measured)

| Spike | Report | Headline |
|-------|--------|----------|
| OCR | [`ocr-spike-report.md`](./ocr-spike-report.md) | PaddleOCR **2.7.3** works; **3.x failed** on this Windows/oneDNN host. Forced OCR on police/insurer/medical/billing pages: mean conf ≈ 0.95–0.99; ~4–11 s/page; peak RSS ~1 GB. Native first is valid for many Amini pages; billing needs OCR (cid). |
| Billing | [`billing-spike-report.md`](./billing-spike-report.md) | Native layer broken; Decimal recovered 8 money tokens + 4 six-digit codes; totals/CPT identity **not** determinable without OCR+layout rules + review issues. |
| DOCX | [`docx-template-spike-report.md`](./docx-template-spike-report.md) | docxtpl dummy multi-section demand generated; Word WYSIWYG still manual; not production letterhead. |

Spikes remain under `spikes/` — **not** incorporated into application architecture.

### Contracts / phases / rules

| Artifact | Result |
|----------|--------|
| [`contract-generation.md`](./contract-generation.md) | Pydantic machine SoT → JSON Schema → generated Zod + CI (no hand duplicates) |
| [`phase-acceptance-matrix.md`](./phase-acceptance-matrix.md) | Phases 0–10 mapped to FR, evidence, fixtures, exit gates |
| `.cursor/rules/veridemand-doctrine.mdc` | Spec hierarchy, one phase, no silent changes, extraction doctrine, deps, exit gates |
| `.cursor/rules/veridemand-evidence.mdc` | Contracts sync, coordinates/money, spikes, gold honesty |

---

## Blockers list (must not be ignored)

### Does **not** block Phase 0 start

- Open decisions OD-03…OD-15 that resolve in later phases  
- Illustrative (non-firm) gold  
- TipTap deferred  
- LibreOffice optional  

### Soft / hard blockers for later phases

| Blocker | Affects | Severity |
|---------|---------|----------|
| Firm-approved gold missing (`todo_verify` / redacted critical facts, no chronology/billing expected tables) | Phases **5, 6, 7, 10** honest exits | **Hard** for claims; demos may use illustrative labels |
| PaddleOCR 3.x broken on measured Windows host; must pin working stack (2.7.3 proven in spike) | Phase **3** production adapter | **Hard** until pin + retest |
| eCW billing native text corrupted; needs OCR + layout-specific parser | Phase **6** | **Hard** for that fixture class |
| DOCX→PDF converter unconfirmed on Windows | Phase **1–2** FR-UPL-06 | Soft |
| Generator package for Zod still to confirm in Phase 0 PR | Phase **0 exit** parity | Soft if Phase 0 selects one |
| Attorney waiver / final confirm policy | Phases **7–9** | Soft until demo |

---

## What was explicitly not done

- No Phase 0 `frontend/` / `backend/` application scaffold  
- No promotion of spike code into services  
- No filling of unknown legal/factual gold values  
- No modification of canonical product specification to clear blockers  

---

## Recommended next step

Begin **Phase 0 — Repository and Contracts** per the acceptance matrix and contract-generation recommendation. Carry OCR pin and gold blockers forward; do not claim Phase 3/5+ exits until those blockers are cleared with evidence.

# Phase 4 — Document Classification and Sequencing — Completion Report

| Field | Value |
|-------|-------|
| **Branch** | `phase-04-document-classification-sequence` |
| **Baseline tag** | `phase-03-audited-pass` (requested; tag not present — baseline commit `4c6672e`, branch tip `db89a3b`) |
| **Starting parent** | `db89a3bd7f5b6ec7feb0f078b99361c135b5f4b5` (Phase 3 hardening re-audit PASS docs) |
| **Report date** | 2026-07-20 |

## Requirements implemented

| FR | Status | Evidence |
|----|--------|----------|
| FR-CLS-01 | Implemented | `score_rules()` + `build_classification_features()`; synthetic + integration tests |
| FR-CLS-02 | Stubbed / disabled | `classify_with_llm_fallback()` provider-neutral stub; `enable_llm_classification=false` |
| FR-CLS-03 | Implemented | Full `DocumentClassification` enum; medical bundle imaging rule |
| FR-CLS-04 | **Deferred** | Strict Phase 4 scope — no metadata `Fact` creation (Phase 5) |
| FR-CLS-05 | Implemented | `propose_sequence()`, PUT `/documents/sequence`, UI reorder |
| FR-CLS-06 | Implemented | Authority defaults + PATCH guard + tests |

## Contract changes (additive)

- `classification.ambiguous` issue type ([`docs/contracts/issue-types.md`](../contracts/issue-types.md))
- `rule_confidence_threshold`, `enable_llm_classification` on AppSettings
- API error codes: `classification_locked`, `document_invalid_patch`, `sequence_invalid`
- Regenerated JSON Schema + Zod (`AppSettings`)

No changes to `Document` wire fields (already defined in contracts v0.1).

## Taxonomy

Canonical 11-value `DocumentClassification` enum unchanged. Rule dictionaries in [`backend/app/services/classification/rules_config.py`](../../backend/app/services/classification/rules_config.py).

## Rule design

- Configuration-driven phrase rules (filename + content + heading weights)
- Usable-span policy respects Phase 3 OCR quality flags (`insufficient_coverage`, failed OCR, etc.)
- Filename-only cap (0.45) when content contradicts filename tokens
- Weak single-keyword insufficient alone

## Rule precedence

Documented in [`docs/readiness/04-classification-thresholds.md`](../readiness/04-classification-thresholds.md): demand/template structural signals → domain content → filename → weak keywords; medical+imaging stays medical; bill+ICD stays bill when billing dominates.

## Confidence policy

- Provisional threshold **0.55** (`RULE_CONFIDENCE_THRESHOLD`)
- Below threshold or ambiguous gap → Amber `classification.ambiguous` Issue
- Confidence is classification confidence, not legal certainty

## Optional LLM status

**Deferred (stub only).** [`backend/app/services/llm/classifier.py`](../../backend/app/services/llm/classifier.py) defines validated request/response shapes; returns `None` when disabled. No provider dependency added.

## Existing-demand authority guard (FR-CLS-06)

- Auto-classified `existing_demand` / `template`: `exclude_from_drafting=true`, `treat_as_secondary_evidence=false`
- Secondary enable via PATCH only for `existing_demand`
- `is_authoritative_evidence()` returns false for excluded/secondary demand (comparison-only; not primary evidence)
- UI warning banner on existing demand rows

## Sequence design

Provisional category rank with upload-order tie-break; existing demand/template at tail. Contiguous `sequence_index`. Atomic PUT reorder validates complete session document set.

## APIs

| Method | Route | Purpose |
|--------|-------|---------|
| (extended) POST | `/api/v1/sessions/{id}/process` | Runs classification after extraction |
| PATCH | `/api/v1/sessions/{id}/documents/{doc_id}` | Classification correction, confirm, exclude, secondary |
| PUT | `/api/v1/sessions/{id}/documents/sequence` | Atomic reorder |

Events: `document.classified` per document.

## Frontend behavior

Documents workspace ([`frontend/src/components/DocumentList.tsx`](../../frontend/src/components/DocumentList.tsx)):

- Type label, confidence, rationale, ambiguous styling
- Classification dropdown + confirm
- Drag-and-drop + keyboard ↑/↓ reorder
- Exclude / secondary-evidence toggles
- Existing-demand non-authoritative warning
- Viewer enabled for `classified` status

## Automated test totals

| Suite | Count |
|-------|-------|
| Backend (full) | **198 passed** |
| Phase 4 new (approx.) | 34 (rules, sequence, authority, integration, delete races) |
| Frontend | 9 passed |

Verification: `node scripts/check-all.mjs` — **PASS** (ruff, mypy, pytest, contract drift ×2, frontend lint/typecheck/test/build).

## Reference-package aggregate results

Local git-ignored Amini reference package **not present** in this workspace. Validated via committed synthetic fixtures mirroring gold expectations ([`docs/example/gold/amini-illustrative.md`](../example/gold/amini-illustrative.md)):

| Safe alias | Expected | Synthetic result |
|------------|----------|------------------|
| Police PDF | `police_report` | PASS |
| Insurer PDF | `insurer_correspondence` | PASS |
| eCW medical export | `medical_record` | PASS |
| eCW billing export | `bill_ledger` | PASS |
| Demand DOCX | `existing_demand`, non-authoritative | PASS |
| Long medical / Jackman | Not run (package absent) | **Gap** |

Reclassification/OCR rerun on PATCH: **not triggered** (integration test).

## Correction timing

Developer PATCH classification + confirm: **< 1 s** (local integration). Manual nontechnical UI walkthrough: **not measured** in this environment (single developer).

Rule classification per synthetic document during process: **sub-second** (dominated by Phase 2/3 extraction in integration tests).

## Lifecycle regression evidence

- `test_classification_delete_races.py`: DELETE during `before_classification_commit` — no late commit, no HTTP 500 (10× stress)
- Phase 3 delete/OCR stress tests: **unchanged PASS**
- Phase 3 OCR init retry, eCW routing: **unchanged PASS**

## Known limitations

- FR-CLS-04 metadata facts deferred to Phase 5
- LLM fallback not live
- Rule thresholds provisional (OD-06)
- Sequence ordering policy provisional (not doctrine-prescribed)
- Reference-package manual acceptance on real Amini files pending local package

## Deferred work

- Phase 5 deterministic fact extraction
- Live LLM classification provider (OD-12)
- Corpus measurement for threshold tuning
- Firm-approved gold eval

## Specification conflicts (reported)

| Conflict | Resolution |
|----------|------------|
| FR-CLS-04 vs Phase 4 strict scope | Deferred FR-CLS-04 |
| `AuthorityMode` vs `treat_as_secondary_evidence` | Contracts win (bool) |
| Module 04 flowchart LLM → `secondary` node | Treated as diagram bug |

## Exit-gate evidence

| Gate | Result |
|------|--------|
| Reference docs classified or correctable without reprocess | PASS (synthetic corpus + PATCH) |
| FR-CLS-06 demand not evidence by default | PASS (automated) |
| Drag-reorder | PASS (API + UI) |
| Classification in seconds | PASS (synthetic) |
| LLM fallback off (nonblocking) | PASS |

## Final verdict

**PASS WITH GAPS** (self-assessment at implementation tip `1556ecc`)

Gaps at completion time: local Amini reference-package acceptance not executed (files absent); FR-CLS-04 deferred; manual nontechnical usability not independently measured.

Do **not** create `phase-04-audited-pass` tag per instructions.

---

## Post-completion audit trail

| Document | Result |
|----------|--------|
| [`phase-04-audit.md`](./phase-04-audit.md) | **FAIL** — B-01/B-02/B-03 (demand authority bypass; high-score review gap) |
| [`phase-04-hardening.md`](./phase-04-hardening.md) | Hardening closes blockers; **READY FOR RE-AUDIT** |

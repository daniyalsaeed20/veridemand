# Gold Case Template

Copy this file for each real or sample matter. Replace every `TODO` placeholder.  
Do not treat the files under `docs/example/` as the only case shape the product must support.

---

## Banner

> **Approval status:** `illustrative` | `pending_firm_review` | `firm_approved`  
> Set to `firm_approved` only after a lawyer/paralegal signs off.

---

## 1. Case metadata

| Field | Value |
|-------|-------|
| `gold_id` | TODO e.g. `gold_matter_001` |
| `label` | TODO short human label |
| `matter_type` | e.g. `motor_vehicle_bi` |
| `corpus_role` | `illustrative_reference` \| `firm_eval` \| `regression` |
| `doi_hint` | TODO date of loss if known (`YYYY-MM-DD`) or `unknown` |
| `notes` | TODO |

### Evidence files (authoritative for extraction)

| display_name | role | notes |
|--------------|------|-------|
| TODO | e.g. police_report | |
| TODO | | |

### Draft / template fixtures (not default evidence)

| display_name | role | notes |
|--------------|------|-------|
| TODO | existing_demand / template | FR-CLS-06: off unless user enables |

---

## 2. Must-find facts

Use types from `docs/contracts/fact-types.md`.

| fact_type | expected_normalized | criticality | source_file_hint | page_hint | status | notes |
|-----------|---------------------|-------------|------------------|-----------|--------|-------|
| TODO | TODO | critical \| normal | TODO | TODO or `unknown` | `expected` \| `todo_verify` | |

**Status meanings**

- `expected` — value believed correct for eval  
- `todo_verify` — confirm after OCR / human review of pages  
- `user_supplied` — cannot be derived; must be entered / queued  

---

## 3. Must-surface issues

Use types from `docs/contracts/issue-types.md`.

| issue_type | severity | blocking | status | notes |
|------------|----------|----------|--------|-------|
| TODO | red \| amber \| green | yes \| no | `expected` \| `todo_verify` | |

---

## 4. Must-queue / Amber-Red expectations

| situation | expected review behavior |
|-----------|--------------------------|
| TODO unreadable handwriting | Red / manual entry |
| TODO low-confidence claim number | Red until confirmed |

---

## 5. Must-not-invent

Values the system must **not** fabricate:

- TODO e.g. settlement amount when TBD  
- TODO e.g. picking one conflicting diagnosis as true  

---

## 6. Objective fact vs attorney judgment

| item | class | notes |
|------|-------|-------|
| TODO | `objective_fact` | From records |
| TODO | `attorney_judgment` | Demand amount, liability framing, etc. |

---

## 7. Export blockers (when draft/export path is under test)

| blocker | issue_type or rule | notes |
|---------|-------------------|-------|
| TODO | e.g. `draft.placeholder` | |

---

## 8. Demand-draft fixture notes (optional)

Only if a demand DOCX is used as a **fixture**, not as evidence:

| pattern | expected preflight / issue | notes |
|---------|----------------------------|-------|
| TODO `[SETTLEMENT AMOUNT - TBD]` | `draft.placeholder` | |

---

## 9. Changelog

| Date | Change |
|------|--------|
| TODO | Initial draft |

# Phase 4 Hardening — Classification Authority Safeguards

**Branch:** `phase-04-audit-hardening`  
**Failed audit:** [`phase-04-audit.md`](./phase-04-audit.md) (commit `43591cd`, tip before hardening)  
**Failed implementation tip:** `1556eccda10fe17cb8399d771ad7c1df7cda4afe`  
**Report date:** 2026-07-20

**Constraints:** No Phase 5 Facts/chronology/billing/contradiction/LLM/drafting/export. No `phase-04-audited-pass` tag.

---

## Final hardening verdict

**READY FOR RE-AUDIT**

Blocking findings B-01, B-02, and B-03 from the independent Phase 4 audit are closed with automated + real-package evidence. A fresh independent re-audit should verify before creating `phase-04-audited-pass`.

---

## Root causes (recorded before / with the fix)

| Blocker | Root cause |
|---------|------------|
| B-01 Amini demand → `police_report` @ 0.85 | Early-page narrative matched Stage B `ct_police`; demand structure weak in early pages; filename weight lost; gap &gt; 0.12 so not ambiguous; **authority defaults keyed only on winning category** |
| B-02 Jackman DOCX → medical/billing | Same Stage B keyword path on demand letters summarizing exams/ICD; treated as primary evidence |
| B-03 High score hides review | Ambiguity ≈ score &lt; 0.55; UI styled only low scores |

No case-specific filename rules were added.

---

## Two-stage architecture

1. **Stage A** — `assess_safety_archetype()` ([`archetype.py`](../../backend/app/services/classification/archetype.py)): structural demand/template/derivative families (≥2 independent families; DOCX multi-evidence summary gate).  
2. **Stage B** — existing `score_rules()` taxonomy.  
3. **Merge** — [`decision.py`](../../backend/app/services/classification/decision.py): archetype overrides evidence labels when demand/template; conflict codes force ambiguous/needs_confirmation even when rule score ≥ 0.55; Stage B demand/template content mirrors into safety when Stage A under-fires.  
4. **Authority policy** — [`authority.py`](../../backend/app/services/classification/authority.py): classification-independent FR-CLS-06; `is_primary_authoritative()` never true under safety restriction.

```text
features → Stage A + Stage B → merge/conflicts → apply_authority_policy → emit document.classified
```

---

## Demand/template safety invariant

```text
safety_archetype ∈ {existing_demand, template, uncertain_derivative}
  ⇒ exclude_from_drafting (unless explicit secondary path for existing_demand)
  ⇒ is_primary_authoritative == false
```

Misclassification as police/medical/billing cannot auto-promote to primary evidence.

---

## Rule-score semantics

Wire field remains `classification_confidence` (contract compatibility). Documented and UI-labeled as **Rule score** (heuristic, not calibrated probability). See [`04-classification-thresholds.md`](../readiness/04-classification-thresholds.md).

New Document fields (additive contracts 0.1):

- `classification_status`: proposed | ambiguous | needs_confirmation | user_confirmed  
- `safety_archetype`: none | existing_demand | template | uncertain_derivative  
- `classification_conflicts`: safe conflict code list  

---

## Real Amini / Jackman package (aliases only)

Local gitignored `docs/example/` processed (~46 s wall). Correction PATCH: **0** extract/OCR reruns; ~5 ms.

| Alias | Category | Rule score | Status | Safety | Primary |
|-------|----------|------------|--------|--------|---------|
| police | police_report | 1.00 | proposed | none | yes |
| insurer | insurer_correspondence | 1.00 | proposed | none | yes |
| ecw_medical | medical_record | 1.00 | proposed | none | yes |
| long_medical | medical_record | 1.00 | ambiguous (close_scores) | none | yes |
| ecw_billing | bill_ledger | 0.45 | ambiguous | none | yes |
| existing_demand | **existing_demand** | 1.00 | ambiguous | **existing_demand** | **no** |
| jackman_demand_1..3 | **existing_demand** | 0.85 | ambiguous | **existing_demand** | **no** |
| template | template | 0.40 | needs_confirmation | template | **no** |

B-01/B-02 closed on real package. Evidence PDFs not incorrectly downgraded to non-primary.

---

## Adversarial / high-score tests

Unit [`test_classification_hardening.py`](../../backend/tests/unit/test_classification_hardening.py) + integration [`test_phase04_hardening.py`](../../backend/tests/integration/test_phase04_hardening.py):

- Demand + police/medical/billing narrative → existing_demand + non-primary  
- Score ≥ 0.55 still ambiguous under conflicts  
- Police mentioning settlement stays police + primary  
- Template restricted  
- Invariant normalize; cannot clear exclude without confirmation  
- LLM disabled → zero provider calls  
- PATCH → zero extract/OCR reruns  

---

## Contract / verification

- Contracts regenerated twice; drift check OK  
- Backend: **213** passed (was 198; +15 hardening)  
- Frontend: **9** passed; production build OK  
- `node scripts/check-all.mjs`: **PASS**

---

## FR-CLS-04

Unchanged nonblocking deferral per Module 04 §10: no Fact entities. Lightweight classification metadata now includes status/safety/conflicts only — not provider/insurer/claimant/date-range Facts (Phase 5 DET).

---

## Known limitations / remaining gaps

- Rule thresholds still provisional (OD-06)  
- LLM live path still stubbed (OD-12)  
- Sequence policy provisional  
- `phase-03-audited-pass` tag may still be absent in some clones (baseline commit OK)  
- Nontechnical multi-user UI timing not measured beyond API (~ms)  
- eCW billing still filename-leaning (0.45) on real package — correctable, not a safety bypass  

---

## Readiness for fresh independent re-audit

Yes — verify B-01/B-02/B-03 closure on tip of `phase-04-audit-hardening`, then decide on immutable tag `phase-04-audited-pass` in a separate procedure. Do not begin Phase 5 in that step.

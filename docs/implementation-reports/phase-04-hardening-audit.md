# Phase 4 Hardening Independent Re-Audit — B-01 / B-02 / B-03

**Audit date:** 2026-07-20  
**Auditor:** Fresh independent verification (not the hardening implementer)  
**Method:** Clean tip verification + authoritative doc/contract review + Stage A/B and authority invariant probes + adversarial synthetic classification + real gitignored reference-package process/classify (aliases only) + conflict/ambiguity and eCW billing policy ruling + instrumented no-reprocessing + sequence + lifecycle races + LLM zero-call proof + frontend review/label audit + contract dual-regen + full `check-all`

**Constraints honored:** No production code changes. No Phase 5 work. No Git tag create/move/delete. Audit probes and private aggregates lived only under gitignored `tmp/audit/`. Private filenames, extracted patient text, screenshots, and credentials were not committed. This report is left **uncommitted** for a separate closure procedure.

**Prior evidence reviewed (not trusted alone):** [`phase-04-audit.md`](./phase-04-audit.md) (FAIL on `1556ecc`), [`phase-04-hardening.md`](./phase-04-hardening.md) (READY FOR RE-AUDIT on `62e1828`).

---

## Final verdict

# PASS

Commit `62e1828a7a32ad0a1909c36dcfc34ebf3b40625d` is suitable for the immutable tag `phase-04-audited-pass`.

All three blocking findings from the failed Phase 4 audit are closed with independent code + API + real-package evidence:

1. **B-01** — Real Amini existing demand classifies as `existing_demand` with `safety_archetype=existing_demand`, `exclude_from_drafting=true`, and `is_primary_authoritative=false` (no longer authoritative `police_report`).
2. **B-02** — Jackman demand DOCX fixtures classify as `existing_demand` with demand safety and non-primary authority (no longer medical/billing primary evidence).
3. **B-03** — Review is driven by `classification_status` / `classification_conflicts` / `safety_archetype` (not score &lt; 0.55 alone); high rule-score conflict cases surface as ambiguous; UI labels **Rule score**.

No blocking regressions. Ordinary evidence (police / insurer / eCW medical / long medical) remains primary where appropriate. Do **not** create the tag in this step; do **not** begin Phase 5. Create `phase-04-audited-pass` only via the separate immutable tagging procedure after this report is committed.

---

## Exact audited commit

| Field | Value |
|-------|-------|
| Branch | `phase-04-audit-hardening` |
| **Audited tip** | `62e1828a7a32ad0a1909c36dcfc34ebf3b40625d` |
| Tip subject | `phase-04: harden classification authority safeguards` |
| Working tree at audit start | Clean |
| Working tree after probes | Clean of production changes; only this report + gitignored `tmp/audit/` |

### Ancestry

| Check | Result |
|-------|--------|
| `4c6672e` (Phase 3 hardening tip) ancestor | Yes |
| `1556ecc` (failed Phase 4 implementation) ancestor | Yes |
| `43591cd` (failed-audit documentation) ancestor | Yes |
| Chain | `4c6672e` → `db89a3b` → `1556ecc` → `43591cd` → `62e1828` |

### Prior tags (unchanged)

`phase-00-pass`, `phase-01-pass`, `phase-01-audited-pass`, `phase-02-audited-pass`  
`phase-03-audited-pass` still **absent** in this clone (baseline commit ancestry OK).  
**No** `phase-04-audited-pass` tag present. No tags created/moved/deleted during this re-audit.

### Diff scope (`43591cd..62e1828` / `1556ecc..62e1828`)

Hardening touches classification Stage A (`archetype*`), authority, decision merge, Document/enums contracts, UI review helpers, fixtures/tests, readiness thresholds, and hardening/completion reports. **No** Fact creation, chronology, billing interpretation, contradiction engine, live LLM HTTP provider, drafting, or export work.

Privacy: `docs/example/*.pdf|*.docx` remain gitignored and untracked. Classification rules / archetype families contain **no** `Amini` / `Jackman` / case-specific identifiers.

---

## Scope result

| Check | Result |
|-------|--------|
| HEAD == `62e1828` | PASS |
| Working tree clean before/after (production) | PASS |
| Descends from Phase 3 baseline + failed audit | PASS |
| Prior phase tags unchanged | PASS (tag absence noted) |
| Diff limited to Phase 4 hardening (+ prior audit docs) | PASS |
| No structured Facts created | PASS |
| No Phase 5+ scope in code | PASS |
| No private case docs committed | PASS |

---

## Blocker closure (independent)

### B-01 — Amini existing demand authority bypass

| Evidence | Result |
|----------|--------|
| Failed audit | `existing_demand` → `police_report` @ 0.85, authoritative |
| Re-audit real package | Alias `existing_demand` → category `existing_demand`, rule score 1.00, status `ambiguous`, safety `existing_demand`, exclude true, **primary false** |
| Stage A | Matched demand families; reason prefix includes `archetype:existing_demand` |
| Authority invariant | PATCH reclassify → `police_report` **keeps** `safety_archetype=existing_demand`; clear exclude without confirm → **400**; confirm+clear exclude still forced back to exclude / non-primary; secondary enable works without becoming primary |

**Closed.**

### B-02 — Jackman demand DOCX as medical/billing primary

| Alias | Category | Rule score | Status | Safety | Primary |
|-------|----------|------------|--------|--------|---------|
| jackman_demand_1 | existing_demand | 0.85 | ambiguous | existing_demand | **no** |
| jackman_demand_2 | existing_demand | 0.85 | ambiguous | existing_demand | **no** |
| jackman_demand_3 | existing_demand | 0.85 | ambiguous | existing_demand | **no** |

Conflicts include `archetype_vs_category` / `weak_single_signal` as applicable. **Closed.**

### B-03 — High-score wrong types not reviewed

| Layer | Finding |
|-------|---------|
| Decision merge | Conflicts / safety force `ambiguous` or `needs_confirmation` even when rule score ≥ 0.55 |
| Adversarial | Demand+police / demand+medical / high_score_conflict_review → status `ambiguous`, primary false |
| UI `needsReview()` | True for `ambiguous` \| `needs_confirmation` \| any conflicts \| any non-`none` safety — **not** score&lt;0.55 only |
| UI label | `Rule score:` (not “Confidence %” as calibrated probability) |

**Closed.**

---

## Stage A / B and authority invariant

### Architecture (verified in code)

1. **Stage A** — `assess_safety_archetype()` structural demand/template/derivative families.  
2. **Stage B** — `score_rules()` taxonomy.  
3. **Merge** — `select_rule_decision(..., archetype=...)` can override evidence category; conflict codes force review.  
4. **Authority** — `apply_authority_policy` / `is_primary_authoritative` / `enforce_authority_invariant` independent of winning category when safety restricts.

### Adversarial synthetic (text probes)

| Case | Category | Safety | Status | Primary |
|------|----------|--------|--------|---------|
| Demand + police narrative | existing_demand | existing_demand | ambiguous | no |
| Demand + medical | existing_demand | existing_demand | ambiguous | no |
| Demand + billing | existing_demand | existing_demand | ambiguous | no |
| Demand structure without word “demand” | existing_demand | existing_demand | ambiguous | no |
| Police mentioning settlement | police_report | none | ambiguous | **yes** (review flagged) |
| Single word “demand” on police | police_report | none | proposed | yes |
| Template + sample placeholders | template | template | ambiguous | no |
| DOCX multi-evidence summary | insurer_correspondence | uncertain_derivative | ambiguous | no |

### Invariant violation attempts

| Attempt | Result |
|---------|--------|
| Clear `exclude_from_drafting` on safety-restricted demand without confirm | 400 `document_invalid_patch` |
| Reclassify real demand → `police_report` | Safety persists; still non-primary |
| Confirm authority + clear exclude while safety=`existing_demand` | Exclude re-enforced; primary remains false |
| Enable secondary on existing_demand | Allowed; primary still false |
| Template / non-demand secondary | Rejected |
| Direct `enforce_authority_invariant` on police+`existing_demand` safety | Exclude forced; primary false |
| Sequence reorder | Does not clear safety / promote primary |
| DELETE during `before_classification_commit` (5×) | 204 delete, subsequent GET 404, no 500 |

**Residual gap (nonblocking):** Short committed synthetic demand fixtures (`write_demand_docx` / `write_demand_with_police_section_pdf`) may leave `safety_archetype=none` while category still excludes. Real-package and rich adversarial text fire Stage A. Category + PATCH guards still prevent silent primary on those fixtures until a user clears exclude after reclassify when safety never fired — acceptable for Phase 4 exit given real-package FR-CLS-06 proof.

---

## Real reference-package classifications

**Package:** gitignored `docs/example/` (aliases via content hash / size ordering only).  
**Probe:** `tmp/audit/phase04_hardening_reaudit_probes.py` → `tmp/audit/phase04_hardening_reaudit.json`.  
**Wall:** ~40 s process+classify.

| Alias | Category | Rule score | Status | Safety | Primary |
|-------|----------|------------|--------|--------|---------|
| police | police_report | 1.00 | proposed | none | yes |
| insurer | insurer_correspondence | 1.00 | proposed | none | yes |
| ecw_medical | medical_record | 1.00 | proposed | none | yes |
| long_medical | medical_record | 1.00 | ambiguous (close_scores) | none | yes |
| ecw_billing | bill_ledger | 0.45 | ambiguous | none | yes |
| existing_demand | existing_demand | 1.00 | ambiguous | existing_demand | **no** |
| jackman_demand_1..3 | existing_demand | 0.85 | ambiguous | existing_demand | **no** |
| template | template | 0.40 | needs_confirmation | template | **no** |

Correction PATCH on `existing_demand`: **~2 ms**, **0** extract/OCR reruns. Classified event messages use safe aggregates only (`category=…;score=…;status=…;safety=…;conflicts=…`) — no private paths/names observed.

Evidence PDFs were **not** incorrectly downgraded to non-primary.

---

## Ambiguity, rule-score semantics, eCW billing ruling

### High score + conflict → review

Confirmed: demand+police and real Jackman/Amini demand cases have rule score ≥ 0.55 yet `classification_status=ambiguous` with conflicts. UI `needsReview` returns true.

### Rule score wording

- Contracts: `classification_confidence` documented as heuristic **rule score**, not calibrated probability (`docs/contracts/entities/document.md`).  
- Readiness: `04-classification-thresholds.md` + UI **Rule score** label.  
- **PASS** for B-03 wording gap from failed audit.

### eCW billing @ 0.45 ambiguous-but-primary

| Question | Ruling |
|----------|--------|
| Does doctrine forbid ordinary evidence from remaining primary while `classification_status=ambiguous`? | **No.** Module 04 routes low confidence / conflicts to Amber review; FR-CLS-06 restricts **existing demand / template** authority, not ordinary evidence primarity. |
| Is `classification_status=ambiguous` the same as verified Facts? | **No.** Status is classification review state only. |
| Blocking for Phase 4? | **No** — filename-leaning bill_ledger @ 0.45 is correctable and review-flagged. |
| Phase 5 implication | Downstream Fact extraction **must not** treat unconfirmed / ambiguous classification as verified evidentiary typing; keep Amber until user confirms. |

---

## Corrections, no-reprocess, sequence, LLM, events

| Check | Result |
|-------|--------|
| PATCH classification / confirm | No native/OCR reruns (instrumented counters 0) |
| PUT sequence | No extract/OCR reruns; latency ~2 ms |
| Real-package correction | 0 extract reruns; ~2 ms |
| `enable_llm_classification` default | `false` |
| LLM provider calls during process (patched counter) | **0** |
| Lifecycle DELETE races | 5/5 OK |
| Event privacy | No Amini/Jackman/path leaks in `document.classified` messages |

---

## Requirement traceability (hardening tip)

| FR | Result |
|----|--------|
| FR-CLS-01 | PASS — Stage A+B + real package types |
| FR-CLS-02 | PASS — disabled by default; 0 calls (OD-12) |
| FR-CLS-03 | PASS — taxonomy intact |
| FR-CLS-04 | Nonblocking deferral — Module 04 §10 Fact metadata deferred; no Phase 5 Facts |
| FR-CLS-05 | PASS — sequence plumbing; no authority side effects |
| FR-CLS-06 | **PASS** on real package + invariant probes |

---

## FR-CLS-04 note

Unchanged from prior audit: Fact-shaped provider/insurer/claimant/date-range extraction remains deferred per Module 04 §10. Hardening added classification status/safety/conflicts only. **Nonblocking.**

---

## Clean verification

| Gate | Result |
|------|--------|
| Backend pytest | **213 passed** (≥213 required) |
| Frontend vitest | **9 passed** |
| Frontend typecheck + production build | PASS |
| Contract generate + drift check | PASS (`contracts:check OK`) |
| `node scripts/check-all.mjs` | PASS |
| Repo-safety (private binaries untracked) | PASS |
| Reference-package classify | Executed (aliases only) |
| No-reprocess / race / LLM probes | PASS |

---

## Residual gaps (nonblocking)

1. **OD-06** — Rule thresholds still provisional.  
2. **OD-12** — Live LLM classification still stubbed / disabled.  
3. **FR-CLS-04** — Fact metadata deferred (Module §10).  
4. **eCW billing** — Ambiguous primary ordinary evidence; allowed; Phase 5 must not equate with verified Facts.  
5. **Synthetic Stage A under-fire** on short committed demand builders; real package + rich probes cover the exit gate.  
6. **`phase-03-audited-pass` tag** may remain absent in some clones (commit ancestry OK).  
7. Nontechnical multi-user UI timing not re-measured beyond API (~ms).

None of these reopen B-01–B-03 or block the Phase 4 hardening exit gate.

---

## Final verdict (restated)

# PASS

Commit `62e1828a7a32ad0a1909c36dcfc34ebf3b40625d` is suitable for the immutable tag `phase-04-audited-pass`.

Do **not** create the tag in this audit step. Do **not** begin Phase 5. Leave this report uncommitted until the separate closure/tagging procedure.

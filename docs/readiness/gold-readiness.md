# Gold-Standard Readiness Audit

**Status date:** 2026-07-19  
**Sources:** [`docs/example/gold/`](../example/gold/), Appendix G  
**Constraint:** Do **not** invent legal or factual values. This audit inventories gaps that prevent objective evaluation.

**Approval status of Amini key:** `illustrative` / `pending_firm_review` — **not** `firm_approved`.

---

## 1. Critical exact facts

From [`amini-illustrative.md`](../example/gold/amini-illustrative.md) §2:

| fact_type | Gold status | Gap type | Blocks honest exit |
|-----------|-------------|----------|--------------------|
| `client.name` | redacted / `todo_verify` | Privacy redaction + unverified | Phase 5, 10 |
| `collision.date` | `2026-03-28` (`expected`) but conflict fixture exists | Conflict resolution is user decision; page_hint `unknown` | Phase 5 (traceability pages); Phase 7 (conflict) |
| `claim.number` | `96A776083-377` marked `todo_verify` — cited from demand fixture | Must confirm in **evidence** spans | Phase 5, 10 |
| `insurer.name` | `todo_verify` (Patriot vs Dairyland tension) | Value not fixed; conflict expected | Phase 5, 7, 10 |
| `insured.name` | `todo_verify` | Missing verified value | Phase 5, 10 |
| `collision.location` | `todo_verify` (inventory hint only) | Unverified | Phase 5, 10 |
| `damages.specials_claimed` | `todo_verify` (~$6783 demand cite) | FR-BIL-04 user confirm | Phase 6, 10 |
| `demand.authorized_amount` | `user_supplied` / TBD | Must-not-invent | Phase 5+ (drafting/export) |

**Also missing for objective eval (not filled in illustrative gold):** DOB, address, policy number, report number, provider identity exact strings — intentionally omitted/redacted; firm gold must supply or mark `must-queue`.

**Lawyer verification required before Phase 5 / 10:** all critical rows above except pure `user_supplied` settlement amount (which must remain blank/TBD until attorney enters).

---

## 2. Chronology facts

| Item | Status | Gap |
|------|--------|-----|
| Authoritative collision date for timeline | Contested (`2026-03-28` vs `2026-03-20` seed) | Gold must list **both candidates** + expected Red issue (already partially done) |
| Provider treatment ranges / visit counts | **Not present** as expected chronology table in illustrative gold | Phase 6 exit needs expected ranges or explicit `todo_verify` queue expectations |
| Imaging event dates | No standalone MRI PDF; embedded imaging only | Classification/chronology must tolerate missing standalone file — gold lacks page-precise imaging events |
| Correspondence date (insurer letter) | Filename hint `06.22.26` only | `todo_verify` from evidence |
| Discharge / settlement timeline events | Not enumerated | Deferred / missing |

**Lawyer verification required before Phase 6 / 10:** provider ranges, visit counts, and which dates belong on the chronology vs attorney narrative.

---

## 3. Billing values

| Item | Status | Gap |
|------|--------|-----|
| Claim-level CPT ledger rows | No gold row-level expected table | Phase 6 billing accuracy metric cannot score objectively |
| Charged / paid / adjustment / balance components | Not listed | Reconciliation gold missing |
| Provider totals | Not listed | Phase 6 exit “match gold totals” blocked |
| `damages.specials_claimed` | `todo_verify` ~$6783 from demand | Must confirm via ledger + FR-BIL-04 |
| Lien amounts | Not listed | Unknown whether present |

**Lawyer / paralegal verification required before Phase 6 / 10:** ledger totals and claimed specials policy for this matter.

---

## 4. Known contradictions

| issue_type | Gold status | Notes | Phase |
|------------|-------------|-------|-------|
| `collision.date_of_loss_conflict` | `expected` | 3/20 vs 3/28 | 7, 10 |
| `medical.fracture_conflict` | `expected` | Chiro X-ray vs MRI narrative (demand flags) | 7, 10 |
| `claim.insurer_conflict` | `expected` | Patriot letter vs Dairyland-named PDF | 7, 10 |
| `draft.placeholder` | `expected` | `[SETTLEMENT AMOUNT - TBD]` | 9, 10 |
| `draft.internal_note` | `expected` | `[FLAG FOR ATTORNEY REVIEW: …]` | 9, 10 |
| `exhibits.listed_missing` | `expected` | Photos/APS/liens listed; files absent | 7–9, 10 |
| `extraction.suspected_handwriting` | `todo_verify` | Possible on scanned stack | 3, 7 |

**Lawyer verification required before Phase 7 / 10:** confirm each contradiction is still expected and severity/blocking flags match firm policy (OD-13).

---

## 5. Draft-defect fixtures

From [`draft-defect-fixtures.md`](../example/gold/draft-defect-fixtures.md) (not full-case gold):

| File | Defects | Eval readiness |
|------|---------|----------------|
| `Demand - Ahmed Ahmed.docx` | Pronoun mismatch | Usable for preflight hygiene tests |
| `Demand - Morris, Sandra.docx` | Empty RE/salutation, pronouns, exhibit gaps | Usable for hygiene; not MV BI product scope |
| `Demand (Fernando Nicolas Fuentes).docx` | Pronoun flip; WPI `[bodily]`/`[mental]` placeholders | Usable for `draft.placeholder` / pronoun |
| `Demand Mayel  Amini Final.docx` | TBD settlement; attorney flags; carrier tension | Comparison / planted defects; **FR-CLS-06 off** |

These fixtures support Phase 9 hygiene gates without firm medical gold. They do **not** replace Amini evidence gold for Phase 5–6.

---

## 6. Attorney-judgment values

| Item | Class | Gold rule |
|------|-------|-----------|
| Settlement / demand amount | `attorney_judgment` | Must-not-invent while TBD |
| Which diagnosis narrative appears in letter | `attorney_judgment` | Must-not auto-pick fracture conflict |
| Liability emphasis / RCW framing | `attorney_judgment` | User/attorney supplied |
| Qualifications / waivers | `attorney_judgment` | Decision log |

**Lawyer verification required before Phase 8–10:** clarify which items remain judgment vs objective extraction for scoring “unsupported statement rate.”

---

## 7. Structural / page-precision gaps

| Gap | Impact |
|-----|--------|
| Many `page_hint: unknown` | Cannot objectively score source-link accuracy until pages verified |
| No firm_approved banner | Phase 10 blind-review packet incomplete |
| No chronology / billing expected tables | Phase 6 metrics incomplete |
| Imaging embedded only | Classification gold must not require standalone MRI PDF |

---

## 8. Values that must be lawyer-verified before phase exit claims

### Before Phase 5 can honestly pass

- `client.name`, `insured.name`, `claim.number` (from evidence), `insurer.name` handling, `collision.location`
- Page-accurate source hints for each must-find critical fact
- Confirm must-not-invent list still correct

### Before Phase 6 can honestly pass

- Provider treatment ranges and visit counts
- Billing ledger expected totals / reconciliation expectations
- Specials claimed confirmation expectation (FR-BIL-04)

### Before Phase 7 can honestly pass

- Confirm each must-surface contradiction still expected
- Severity / blocking policy for insurer conflict and exhibits
- Handwriting / unreadable page expectations after OCR measurement

### Before Phase 10 can honestly pass

- All of the above under `firm_approved`
- Blind-review packet baselines (current ChatGPT/Claude workflow timings) — **not present**
- Controlled gold path outside illustrative `docs/example/gold/` (Module 12 open item)

---

## 9. Verdict on gold readiness

| Question | Answer |
|----------|--------|
| Sufficient for Phase 0 harness **shape**? | **Yes** |
| Sufficient for honest Phase 5–7 / 10 exit gates? | **No** |
| May demos use illustrative keys with explicit labeling? | **Yes**, if reports say `illustrative` and do not claim firm-approved accuracy |

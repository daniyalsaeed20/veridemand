# Spec Conflicts (Pre-Implementation Readiness)

**Status date:** 2026-07-19  
**Resolution hierarchy (doctrine):**

1. [`docs/prototype_documentation.md`](../prototype_documentation.md) — product doctrine and architecture  
2. [`docs/contracts/`](../contracts/) — field shapes, enums, fact/issue types, error codes (**contracts win** on shapes)  
3. [`docs/modules/`](../modules/) — module design / flows (must not redefine field shapes)  
4. [`docs/example/gold/`](../example/gold/) — illustrative eval keys only  
5. [`docs/readiness/`](./) — readiness evidence; **not** doctrine  

This file lists **documented divergences or friction points**, not new requirements.

---

## SC-01 — Conceptual entity tables vs contracts field packs

| Item | Detail |
|------|--------|
| **Where** | Prototype §7.2 entity overview table vs `docs/contracts/entities/*` |
| **Nature** | §7.2 is explicitly conceptual; contracts hold machine fields. |
| **Resolution** | If prose conflicts with contracts, **contracts win** (stated in §7.2 callout and every module §7). |
| **Action** | Implementers use contracts; do not implement from §7.2 alone. |
| **Blocking?** | No |

---

## SC-02 — Deprecated aliases still mentioned historically

| Item | Detail |
|------|--------|
| **Where** | `FactCandidate` vs `Fact`; SessionStatus `active` vs precise workflow states |
| **Nature** | Contracts README deprecates aliases; some older narrative may still say “candidates.” |
| **Resolution** | Use `Fact` + `FactStatus`; never emit `active` or `FactCandidate` in new APIs ([`enums.md`](../contracts/enums.md), [`fact.md`](../contracts/entities/fact.md)). |
| **Blocking?** | No if Phase 0 schemas omit aliases |

---

## SC-03 — Phase number ≠ Module file number ≠ UI step

| Item | Detail |
|------|--------|
| **Where** | Roadmap Phase 9 ↔ Module 10; Phase 10 ↔ Module 12; Module 11 optional out of order |
| **Nature** | Easy to implement the wrong module for a phase. |
| **Resolution** | Use crosswalk in [`docs/modules/README.md`](../modules/README.md#phase--module--ui-crosswalk). Do not invent a third map. |
| **Blocking?** | Process risk only |

---

## SC-04 — Contracts README “hand-maintain Zod” vs Module 00 “JSON Schema → Zod”

| Item | Detail |
|------|--------|
| **Where** | [`contracts/README.md`](../contracts/README.md) schema mirror path; Module 00 §2 / §5.1 / §10 |
| **Nature** | Temporary hand mirrors are allowed “until CI generation,” while Module 00 states Pydantic → JSON Schema → Zod validation intent. |
| **Resolution** | Not a doctrine conflict: Markdown contracts remain human SoT; readiness recommends **generated** frontend schemas ([`contract-generation.md`](./contract-generation.md)). Hand mirrors are a bootstrap stopgap, not the end state. |
| **Blocking?** | Soft — Phase 0 exit needs a chosen parity mechanism (OD-02) |

---

## SC-05 — OCR strategy narrative vs numeric SoT location

| Item | Detail |
|------|--------|
| **Where** | Prototype §9 vs [`03-ocr-thresholds.md`](../modules/03-ocr-thresholds.md) vs `AppSettings` |
| **Nature** | §9 is strategy; numeric knobs live in thresholds addendum / AppSettings. Appendix D notes prefer contracts entity + thresholds after calibration if values diverge. |
| **Resolution** | Implement knobs from `AppSettings` + thresholds addendum; keep §9 for policy narrative (no global confidence cutoff). |
| **Blocking?** | No |

---

## SC-06 — Issue blocking flags: entity `blocking` vs informal `blocks_drafting` / `blocks_export`

| Item | Detail |
|------|--------|
| **Where** | Module 07 notes; [`issue.md`](../contracts/entities/issue.md) `blocking` field |
| **Nature** | Informal dual flags in design prose vs single contracted `blocking`. |
| **Resolution** | Prefer `Issue.blocking` (contracts). Map any UI “blocks draft/export” to that field. |
| **Blocking?** | No |

---

## SC-07 — Gold illustrative values vs Phase exit gates that assume gold truth

| Item | Detail |
|------|--------|
| **Where** | [`amini-illustrative.md`](../example/gold/amini-illustrative.md) `illustrative` / `todo_verify` vs Phase 5–7, 10 exit gates |
| **Nature** | Gates say “match the gold set”; gold says not lawyer-final. |
| **Resolution** | Treat illustrative gold as **harness shape / planted defects**. Honest exit requires `firm_approved` gold (OD-07). Do **not** rewrite the product spec to weaken gates. |
| **Blocking?** | Blocks honest Phase 5/6/7/10 claims; not Phase 0 |

---

## SC-08 — Appendix G corpus inventory vs privacy / public-repo guidance

| Item | Detail |
|------|--------|
| **Where** | Appendix G lists real sample filenames; gold README says keep binaries out of public repos / LLM pipelines |
| **Nature** | Local controlled corpus exists under `docs/example/`; publishing it would conflict with privacy guidance. |
| **Resolution** | Keep binaries local/controlled; readiness spikes read locally; do not paste PII into readiness reports beyond existing illustrative notes. |
| **Blocking?** | No for local Phase 0 |

---

## SC-09 — TipTap listed in stack vs secondary to docxtpl

| Item | Detail |
|------|--------|
| **Where** | §6.2 TipTap row; Phase 8 deliverables; Module 09 |
| **Nature** | TipTap is in the selected stack table but explicitly **secondary** after docxtpl proves the loop. |
| **Resolution** | Not a conflict: TipTap is optional polish; Phase 8 exit is editable DOCX via docxtpl. |
| **Blocking?** | No |

---

## SC-10 — Ephemeral helper types (`FactReview`, `FactGroup`, `ReviewItem`) vs queue SoT

| Item | Detail |
|------|--------|
| **Where** | Contracts README “Derived / ephemeral types”; Modules 05/07/08 |
| **Nature** | Helpers must not become separate persisted entities. |
| **Resolution** | Session queue SoT remains `Issue`; helpers create/update Issues/Facts only. |
| **Blocking?** | No |

---

## SC-11 — Filename note: Amini demand DOCX spacing

| Item | Detail |
|------|--------|
| **Where** | Gold / Appendix G `Demand Mayel Amini Final.docx` vs on-disk `Demand Mayel  Amini Final.docx` (extra space) |
| **Nature** | Path mismatch risk for fixtures/tests. |
| **Resolution** | Tests must resolve actual filesystem name; do not change product doctrine. Document in implementation dependencies. |
| **Blocking?** | Soft for fixture loaders |

---

## Non-conflicts (explicitly aligned)

- LLM not primary extractor (prototype v0.2, modules 03/05/11).  
- Money as decimal strings in JSON / `Decimal` in code (contracts + Module 06).  
- Coordinates normalized top-left `[0,1]` (§7.3 + SourceToken/SourceSpan).  
- Free/local OCR preference; no paid DocAI in prototype.

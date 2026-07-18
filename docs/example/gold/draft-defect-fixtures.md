# Draft Defect Fixtures (Illustrative)

> **Not full case gold.** These sample Jackman-style demand DOCX files under `docs/example/` are **draft hygiene / preflight fixtures** only. They are not complete evidence packages and do not define product scope.

Use with verification / export modules (placeholders, pronouns, incomplete RE blocks).  
`fact_type` / `issue_type` from `docs/contracts/`.

---

## `Demand - Ahmed Ahmed.docx`

| Defect pattern | issue_type | severity | notes |
|----------------|------------|----------|-------|
| Pronoun mismatch (e.g. “her” for male client in specials narrative) | `draft.pronoun_mismatch` | amber/red | Detect in draft hygiene / preflight |
| Minor cite punctuation glitches | `draft.internal_note` or hygiene warning | green/amber | Optional |

**Role:** completed-style demand sample for pronoun checks — **not** an evidence corpus.

---

## `Demand - Morris, Sandra.docx`

| Defect pattern | issue_type | severity | notes |
|----------------|------------|----------|-------|
| Empty insured / claim fields in RE block | `user_input.unresolved_attorney_decision` or identity/claim gap | red/amber | Incomplete letter metadata |
| Salutation “Dear ” with missing name | draft hygiene / missing adjuster | amber | |
| Plural “our clients” / wrong pronoun (“his claim”) | `draft.pronoun_mismatch` | amber/red | |
| Exhibit photos listed but not in folder | `exhibits.listed_missing` | amber | |

**Role:** long narrative demand sample for RE/salutation/exhibit gap checks. Matter type in the letter may differ from MV BI — still only a **fixture**, not a second product vertical requirement.

---

## `Demand (Fernando Nicolas Fuentes).docx`

| Defect pattern | issue_type | severity | notes |
|----------------|------------|----------|-------|
| Pronoun flip (“his” / “her”) in demand paragraph | `draft.pronoun_mismatch` | amber/red | |
| Leftover WPI template brackets `[bodily]` / `[mental]` | `draft.placeholder` | red | |
| Prior plantar fasciitis / aggravation theme | — | — | Useful later for `prior.*` / conflict demos when paired with real records (not present in this folder) |

**Role:** draft placeholder + pronoun fixture; aggravation theme is illustrative only without evidence PDFs.

---

## How to apply in tests

1. Do **not** run these three files through the full evidence extraction MVP as if they were complete cases.  
2. Prefer loading text via DOCX extractors and running **draft hygiene / preflight** rules.  
3. For end-to-end evidence+gold shape, use [`amini-illustrative.md`](./amini-illustrative.md) (and real firm gold for production eval).

## Changelog

| Date | Change |
|------|--------|
| 2026-07-18 | Initial draft-defect fixtures (Pass 2) |

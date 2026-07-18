# Gold Case: Amini (Illustrative Reference Only)

> **Example only — replace with firm-approved gold for production eval.**  
> **Approval status:** `illustrative` / `pending_firm_review`  
> **corpus_role:** `illustrative_reference`  
> This package demonstrates gold-key shape and planted eval defects. It does **not** define product scope or the only real-world case shape.

---

## 1. Case metadata

| Field | Value |
|-------|-------|
| `gold_id` | `gold_amini_illustrative_v0` |
| `label` | Amini MV BI sample package |
| `matter_type` | `motor_vehicle_bi` |
| `corpus_role` | `illustrative_reference` |
| `doi_hint` | `2026-03-28` (also conflict fixture at `2026-03-20` — see issues) |
| `notes` | Built from Appendix G + prior corpus inventory. Page-precise OCR not required for this pass; many rows are `todo_verify`. |

### Evidence files (authoritative for extraction demos)

| display_name | role | notes |
|--------------|------|-------|
| `EG90156.pdf` | police_report | ~4 pages; often OCR-first |
| `Mayel Amini Dairyland Insurance 06.22.26.pdf` | insurer_correspondence | Scanned; filename says Dairyland |
| `AMINI_MAYEL_20260706_eCW Medical Records.pdf` | medical_record | Digital EMR-style export |
| `AMINI_MAYEL_20260706_eCW Billing Ledger.pdf` | bill_ledger | Claim-level CPT ledger |
| `MEDICAL RECORDS- AMINI MAYEL DOI 03-28-2026- JACKMAN LAW FIRM.pdf` | medical_record | ~67-page scanned clinical/chiro stack |

### Draft / template fixtures (not default evidence)

| display_name | role | notes |
|--------------|------|-------|
| `Demand Mayel Amini Final.docx` | existing_demand | Comparison / planted defects only; **FR-CLS-06 off by default** |

**Imaging:** No standalone MRI PDF in the sample folder; imaging content may appear inside medical bundles — classification should tolerate embedded imaging.

---

## 2. Must-find facts

Use types from `docs/contracts/fact-types.md`.

| fact_type | expected_normalized | criticality | source_file_hint | page_hint | status | notes |
|-----------|---------------------|-------------|------------------|-----------|--------|-------|
| `client.name` | *(redact in public copies; match evidence)* | critical | police / eCW / medical stack | unknown | `todo_verify` | Confirm from evidence, not demand alone |
| `collision.date` | `2026-03-28` | critical | `EG90156.pdf`, medical stack filename DOI | unknown | `expected` | Primary DOL used in package naming; **conflict exists** — see issues |
| `claim.number` | `96A776083-377` | critical | demand fixture cites; verify in evidence | unknown | `todo_verify` | Confirm on insurer/police/medical before treating as gold |
| `insurer.name` | *(todo_verify — Patriot vs Dairyland tension)* | critical | demand fixture vs Dairyland-named PDF | unknown | `todo_verify` | Must surface conflict; do not silently pick one |
| `insured.name` | *(todo_verify from police/demand)* | critical | `EG90156.pdf` | unknown | `todo_verify` | |
| `collision.location` | *(todo_verify — I-5 / Kent Des Moines Rd area per prior inventory)* | critical | police / demand fixture | unknown | `todo_verify` | |
| `damages.specials_claimed` | *(todo_verify; demand fixture cited ~$6783)* | critical | billing ledger + user confirm | unknown | `todo_verify` | FR-BIL-04: user confirm when not determinable |
| `demand.authorized_amount` | — | critical | — | — | `user_supplied` | Demand has TBD; must **not** invent |

Privacy: do not paste full addresses, DOBs, or clinical narratives into public docs. Firm-internal gold may fill redacted cells after review.

---

## 3. Must-surface issues

| issue_type | severity | blocking | status | notes |
|------------|----------|----------|--------|-------|
| `collision.date_of_loss_conflict` | red | yes | `expected` | Demand flags ~`2026-03-20` (Coast) vs `2026-03-28` elsewhere |
| `medical.fracture_conflict` | red | yes | `expected` | Chiro X-ray / compression fracture narrative vs later MRI without fracture (demand attorney flags) |
| `claim.insurer_conflict` | amber/red | yes if unresolved for letter header | `expected` | Patriot (demand letter) vs Dairyland-named insurer PDF |
| `draft.placeholder` | red | yes (export) | `expected` | `[SETTLEMENT AMOUNT - TBD]` on demand fixture |
| `draft.internal_note` | red | yes (export) | `expected` | `[FLAG FOR ATTORNEY REVIEW: …]` blocks on demand fixture |
| `exhibits.listed_missing` | amber/red | depends | `expected` | Photos / APS / liens listed in demand; not all present as separate files in folder |
| `extraction.suspected_handwriting` | amber/red | if critical field | `todo_verify` | Possible on scanned chiro stack; queue rather than invent |

---

## 4. Must-queue / Amber-Red expectations

| situation | expected review behavior |
|-----------|--------------------------|
| Scanned police / insurer / long clinical pages fail native text | OCR path or page quality warning; never silent empty |
| Conflicting DOL values | Red issue; no auto-winner |
| Fracture vs no-fracture tension | Red medical issue; no silent diagnosis pick |
| Handwriting / illegible fields | Red/Amber + manual entry (optional crop assist) |
| Settlement amount | User-supplied or block drafting — not derived |

---

## 5. Must-not-invent

- Authorized settlement / demand dollar amount while TBD remains  
- A single “true” DOL when conflict is open  
- A single “true” fracture diagnosis when conflict is open  
- Missing exhibit images that are not in the upload set  
- Claim/policy numbers not present in evidence spans (unless user-entered with source)

---

## 6. Objective fact vs attorney judgment

| item | class | notes |
|------|-------|-------|
| Collision date candidates from records | `objective_fact` | Conflict resolution is a user decision |
| Imaging/chiro findings as stated in records | `objective_fact` | |
| Which diagnosis narrative to put in the letter | `attorney_judgment` | |
| Settlement amount and offer framing | `attorney_judgment` | |
| Liability emphasis / RCW framing | `attorney_judgment` | |

---

## 7. Export blockers (draft/export path)

| blocker | issue_type or rule | notes |
|---------|-------------------|-------|
| TBD settlement | `draft.placeholder` | Demand fixture |
| Attorney review flags left in | `draft.internal_note` | Demand fixture |
| Unresolved Red DOL / fracture issues | `collision.date_of_loss_conflict`, `medical.fracture_conflict` | If those facts used in draft |
| Missing demand amount | `user_input.missing_demand_amount` | |

---

## 8. Demand-draft fixture notes

**Source role:** `demand_draft_fixture` — **excluded** from default evidence extraction unless the user enables secondary evidence (FR-CLS-06).

| pattern | expected preflight / issue | notes |
|---------|----------------------------|-------|
| `[SETTLEMENT AMOUNT - TBD]` | `draft.placeholder` | Blocks final export |
| `[FLAG FOR ATTORNEY REVIEW: …]` (DOL / MRI vs X-ray) | `draft.internal_note` + related medical/collision issues | Human-in-the-loop demo |
| Carrier naming in letter vs Dairyland PDF filename | `claim.insurer_conflict` | Do not resolve silently |

Use this DOCX to test **preflight and issue surfacing**, not as the gold source for medical facts.

---

## 9. Changelog

| Date | Change |
|------|--------|
| 2026-07-18 | Initial illustrative gold from Appendix G / inventory (Pass 2) |

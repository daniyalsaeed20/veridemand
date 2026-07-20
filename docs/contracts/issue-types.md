# Issue Type Catalog

**contracts_version:** `0.1`  
**Status:** `canonical_v0.1` — **additive** (new types may be added; do not silently rename)

Source: prototype Appendix B, normalized to dotted `issue_type` strings (`category.specific`).

Use these values in `Issue.issue_type`.

| issue_type | Category | Typical severity | Notes |
|------------|----------|------------------|-------|
| `extraction.unreadable_page` | Extraction | red/amber | |
| `extraction.low_ocr_confidence` | Extraction | amber/red | Criticality-aware |
| `extraction.broken_text_layer` | Extraction | amber | |
| `extraction.truncated_text` | Extraction | amber | |
| `extraction.suspected_handwriting` | Extraction | red | Manual completion |
| `extraction.insufficient_ocr_coverage` | Extraction | amber | Under-detection on ink-rich page; tokens suppressed |
| `identity.name_conflict` | Identity | red | |
| `identity.dob_conflict` | Identity | red | |
| `identity.pronoun_conflict` | Identity | amber/red | |
| `identity.address_conflict` | Identity | amber | |
| `claim.claim_number_conflict` | Claim | red | |
| `claim.policy_number_conflict` | Claim | red | |
| `claim.insurer_conflict` | Claim | red | e.g. carrier naming tension |
| `collision.date_of_loss_conflict` | Collision | red | Amini-style DOL conflict |
| `collision.location_conflict` | Collision | amber/red | |
| `collision.liability_narrative_conflict` | Collision | amber | |
| `medical.diagnosis_conflict` | Medical | red | |
| `medical.fracture_conflict` | Medical | red | X-ray vs MRI tension |
| `medical.symptom_status_conflict` | Medical | amber | |
| `medical.prior_condition_conflict` | Medical | amber/red | |
| `medical.future_care_conflict` | Medical | amber | |
| `billing.unreconciled_balance` | Billing | amber/red | |
| `billing.duplicate_charge` | Billing | amber | |
| `billing.total_mismatch` | Billing | red | |
| `billing.missing_bill` | Billing | amber | |
| `billing.missing_lien` | Billing | amber | |
| `draft.placeholder` | Draft | red | e.g. TBD settlement |
| `draft.internal_note` | Draft | red | Attorney flags left in |
| `draft.unsupported_statement` | Draft | red | |
| `draft.contradicted_statement` | Draft | red | |
| `draft.pronoun_mismatch` | Draft | amber/red | |
| `draft.duplicate_section` | Draft | amber | |
| `exhibits.listed_missing` | Exhibits | amber/red | |
| `exhibits.uploaded_unlisted` | Exhibits | amber | |
| `exhibits.wrong_numbering` | Exhibits | amber | |
| `user_input.missing_demand_amount` | User input | red | Blocks drafting |
| `user_input.missing_deadline` | User input | amber/red | |
| `user_input.unresolved_attorney_decision` | User input | red | |

## Changelog

| Version | Change |
|---------|--------|
| 0.1 | Initial catalog from Appendix B (dotted form) |

# Fact-Type → Parser Catalog (Module 05 Addendum)

| Field | Value |
|-------|-------|
| `parser_catalog_version` | `0.1-provisional` |
| Spec | §8.5 FR-DET-01..06 |
| Owning module | [05 Deterministic Fact Extraction](./05-deterministic-fact-extraction.md) |
| Fact types | [`docs/contracts/fact-types.md`](../contracts/fact-types.md) |
| Fact entity | [`docs/contracts/entities/fact.md`](../contracts/entities/fact.md) |
| DocumentClassification | [`docs/contracts/enums.md`](../contracts/enums.md) |
| Review bands | [`03-ocr-thresholds.md`](./03-ocr-thresholds.md) §5 |

## Purpose and doctrine

Maps each MVP `fact_type` to a deterministic parser: **label cues + local context + value pattern + normalizer**. No LLM. No inventing missing values (FR-DET-06). Regex alone is insufficient (FR-DET-03)—require label/context grouping.

**Illustrative samples:** Label phrases below are **reusable** patterns (police reports, EMR, ledgers, insurer letters). Mentions of “sample package” are optional hints only—`docs/example/` is not product scope.

**Additive:** Grow this catalog when gold/eval misses appear; do not silently rename `parser_id`s once tests depend on them.

---

## 1. Registry model

`FactService` loads a registry: `parser_id` → callable.

```text
for each document (optionally filtered by DocumentClassification):
  spans/tokens → for each registered parser with matching doc classes:
    find label hits → take context window → parse value → normalize →
    attach source_span_ids → score confidence → emit Fact (suggested)
```

| Component | Role |
|-----------|------|
| `parser_id` | Stable id e.g. `det.collision.date.v1` |
| Label cues | Case-insensitive phrase / form-field synonyms |
| Value pattern | Regex or structured pattern sketch (implement in code) |
| `normalize_*` | Shared helper producing typed `normalized_value` |
| Doc classes | Preferred `DocumentClassification` filters (not exclusive if label matches elsewhere) |

Proposed helpers (module 05): `parse_dates`, `parse_times`, `parse_identifiers`, `parse_money`, `parse_cpt_codes`, `parse_icd10_codes`, `parse_provider_names`, `group_by_label_and_context`, `score_candidate_confidence`, `link_source_spans`.

---

## 2. Shared normalizers

| Helper | Input | Output |
|--------|-------|--------|
| `normalize_date` | raw date string | `YYYY-MM-DD` or null + review |
| `normalize_time` | raw time | `HH:MM` (24h) or null |
| `normalize_name` | person/org string | trimmed collapsed whitespace; preserve raw |
| `normalize_identifier` | claim/policy/report | alnum + allowed punctuation; strip spaces |
| `normalize_currency` | money text | decimal string e.g. `"1234.56"` |
| `normalize_code` | CPT/ICD | canonical code string |
| `normalize_pronoun_set` | he/she/they text | `he` \| `she` \| `they` \| null |

Invalid normalize → do not invent; emit Amber/Red per criticality.

---

## 3. Context-window rule (provisional)

| Setting | Provisional default | Notes |
|---------|---------------------|-------|
| Same-line preference | on | Value to the right of label on same line first |
| Token window | ± `12` tokens | If not same-line |
| Vertical neighbors | ± `1` line | Form fields / tables |
| Max label–value distance | `80` chars | Beyond → weaker confidence |

Ambiguous multi-hits: keep **all** candidates; let IssueService detect exact conflicts—never pick a silent winner.

---

## 4. MVP parser catalog

Columns: miss severity uses criticality + [OCR review matrix](./03-ocr-thresholds.md).

### 4.1 Identity

| fact_type | parser_id | Label cues (examples) | Value pattern sketch | Normalizer | Doc classes | Crit. | Miss → | Status |
|-----------|-----------|----------------------|----------------------|------------|--------------|-------|--------|--------|
| `client.name` | `det.client.name.v1` | Patient, Claimant, Plaintiff, Name of Injured | Person name tokens | `normalize_name` | medical_record, police_report, bill_ledger | critical | Red if absent | mvp |
| `client.dob` | `det.client.dob.v1` | DOB, Date of Birth, Birth Date | US/ISO date | `normalize_date` | medical_record, police_report | critical | Red | mvp |
| `client.address` | `det.client.address.v1` | Address, Residence, Patient Address | multi-token address | trim/preserve | medical_record | normal | Amber | mvp |
| `client.pronouns` | `det.client.pronouns.v1` | Sex, Gender, He/She (weak) | M/F/X or he/she/they | `normalize_pronoun_set` | medical_record | critical | Amber/Red for draft | mvp (light) |
| `attorney.name` | `det.attorney.name.v1` | Attorney, Counsel, Law Firm (letterhead) | person/org | `normalize_name` | existing_demand, template, other | normal | Amber | mvp |

### 4.2 Claim / insurer

| fact_type | parser_id | Label cues | Value pattern sketch | Normalizer | Doc classes | Crit. | Miss → | Status |
|-----------|-----------|------------|----------------------|------------|--------------|-------|--------|--------|
| `insurer.name` | `det.insurer.name.v1` | Insurer, Insurance Company, Carrier, Claims | org name | `normalize_name` | insurer_correspondence, police_report | critical | Red; conflict if multiple | mvp |
| `insured.name` | `det.insured.name.v1` | Insured, Your Insured, Driver (at-fault) | person name | `normalize_name` | police_report, insurer_correspondence | critical | Red | mvp |
| `adjuster.name` | `det.adjuster.name.v1` | Adjuster, Claim Representative | person name | `normalize_name` | insurer_correspondence | normal | Amber | mvp |
| `claim.number` | `det.claim.number.v1` | Claim No, Claim Number, Claim # | alnum + `-` | `normalize_identifier` | insurer_correspondence, bill_ledger | critical | Red | mvp |
| `policy.number` | `det.policy.number.v1` | Policy No, Policy Number, Policy # | alnum + `-` | `normalize_identifier` | insurer_correspondence | critical | Red | mvp |

### 4.3 Collision / citation

| fact_type | parser_id | Label cues | Value pattern sketch | Normalizer | Doc classes | Crit. | Miss → | Status |
|-----------|-----------|------------|----------------------|------------|--------------|-------|--------|--------|
| `collision.date` | `det.collision.date.v1` | Date of Loss, DOL, Date of Collision, Accident Date | date | `normalize_date` | police_report, medical_record, insurer_correspondence | critical | Red; multi-value → conflict issue | mvp |
| `collision.time` | `det.collision.time.v1` | Time of Loss, Time of Accident | time | `normalize_time` | police_report | normal | Amber | mvp |
| `collision.location` | `det.collision.location.v1` | Location, Place of Accident, Intersection | place text | trim | police_report | critical | Amber/Red | mvp |
| `collision.vehicles` | `det.collision.vehicles.v1` | Vehicle, Unit 1/2, Make/Model | free text / structured | trim | police_report | normal | Amber | mvp |
| `liability.citation` | `det.liability.citation.v1` | Citation, Citation No, Infraction | id | `normalize_identifier` | police_report | normal | Amber | mvp |
| report number (maps to claim or collision meta) | `det.collision.report_number.v1` | Report No, Case No, Incident No | id | `normalize_identifier` | police_report | critical-ish | Amber/Red | mvp — store as `claim.number` only if clearly claim; else note in `label_context` / extend taxonomy later |

Also extract phones/emails when labeled (FR-DET-01) as optional `client`/`provider` contact facts if added to taxonomy later; until then keep as generic identifier candidates in session debug only—or add additive types when needed.

### 4.4 Medical / imaging (exact)

| fact_type | parser_id | Label cues | Value pattern sketch | Normalizer | Doc classes | Crit. | Miss → | Status |
|-----------|-----------|------------|----------------------|------------|--------------|-------|--------|--------|
| `medical.provider` | `det.medical.provider.v1` | Provider, Rendering Provider, Facility, Clinic | org/person | `normalize_name` | medical_record, bill_ledger | normal | Amber | mvp |
| `medical.visit_date` | `det.medical.visit_date.v1` | DOS, Date of Service, Visit Date, Encounter Date | date | `normalize_date` | medical_record, bill_ledger | normal | Amber | mvp |
| `medical.diagnosis` | `det.medical.diagnosis.icd.v1` | Diagnosis, ICD, ICD-10, Dx | `^[A-TV-Z][0-9][0-9A-Z](\.[0-9A-Z]{1,4})?$` style | `normalize_code` | medical_record, bill_ledger | critical | Amber; text-only dx without code → weaker / review | mvp (code-first) |
| `imaging.study_date` | `det.imaging.study_date.v1` | Study Date, Exam Date, MRI Date | date | `normalize_date` | medical_record, imaging_report | normal | Amber | mvp |
| `imaging.modality` | `det.imaging.modality.v1` | Modality, MRI, X-ray, CT | enum-ish keywords | lowercase token | medical_record, imaging_report | normal | Amber | mvp |
| `imaging.fracture` | — | — | — | — | — | critical | — | **deferred** narrative; conflict via IssueService when both “fracture” and “no fracture” spans exist (rules may flag keyword co-occurrence without asserting truth) |

### 4.5 Billing / damages

| fact_type | parser_id | Label cues | Value pattern sketch | Normalizer | Doc classes | Crit. | Miss → | Status |
|-----------|-----------|------------|----------------------|------------|--------------|-------|--------|--------|
| `damages.charge` | `det.damages.charge.v1` | Charge, Amount, Billed | currency | `normalize_currency` | bill_ledger | normal | Amber | mvp — prefer BillingEntry rows |
| `damages.payment` | `det.damages.payment.v1` | Payment, Paid, Ins Pay | currency | `normalize_currency` | bill_ledger | normal | Amber | mvp |
| `damages.adjustment` | `det.damages.adjustment.v1` | Adjustment, Adj, Write-off | currency | `normalize_currency` | bill_ledger | normal | Amber | mvp |
| `damages.balance` | `det.damages.balance.v1` | Balance, Amount Due, Patient Bal | currency | `normalize_currency` | bill_ledger | normal | Amber; reconcile in BillingService | mvp |
| CPT (line code) | `det.billing.cpt.v1` | CPT, Procedure Code | 5-digit CPT | `normalize_code` | bill_ledger | normal | Amber | mvp — attach on BillingEntry + optional fact |
| `damages.specials_claimed` | `det.damages.specials_claimed.v1` | Medical Specials, Total Specials | currency | `normalize_currency` | bill_ledger, existing_demand | critical | **User confirm** (FR-BIL-04) if not uniquely determined | mvp |
| `damages.lien` | `det.damages.lien.v1` | Lien, Lien Amount | currency | `normalize_currency` | lien, bill_ledger | normal | Amber | mvp |

Calculations (`calculate_service_ranges`, `count_visits`, `sum_money`) are **code**, not parsers—inputs are dated visits and BillingEntry lines.

### 4.6 Demand parameters (user-supplied)

| fact_type | parser_id | Notes | Status |
|-----------|-----------|-------|--------|
| `demand.authorized_amount` | — | Never invent from records; UI entry / block drafting | `user_supplied` |
| `demand.offer_expiry` | — | User/attorney supplied | `user_supplied` |
| `demand.multiplier` | — | Firm policy / user | `user_supplied` |
| `demand.exhibit_order` | — | User/template | `user_supplied` |

If a demand DOCX is enabled as secondary evidence (FR-CLS-06), still do **not** treat TBD settlement as extracted truth—preflight `draft.placeholder` applies.

### 4.7 Correspondence (light MVP)

| fact_type | parser_id | Label cues | Normalizer | Crit. | Status |
|-----------|-----------|------------|------------|-------|--------|
| `correspondence.offer_deadline` | `det.corr.offer_deadline.v1` | Offer expires, Respond by, Deadline | `normalize_date` | critical | mvp |
| `correspondence.response_deadline` | `det.corr.response_deadline.v1` | Please respond by, Due Date | `normalize_date` | normal | mvp |

---

## 5. Deferred (not DET-primary)

Do **not** ship fake regex for narrative semantics. Leave for review, chronology summaries, or optional Module 11 later.

| fact_type | Reason |
|-----------|--------|
| `medical.complaint`, `medical.exam_finding`, `medical.treatment`, `medical.medication`, `medical.pain_score` | Narrative / list extraction beyond exact codes |
| `imaging.finding`, `imaging.measurement`, `imaging.stenosis`, `imaging.recommendation` | Semantic radiology language |
| `recovery.*`, `prior.*` | Narrative / opinion |
| `liability.admission`, `liability.police_finding`, `liability.witness`, `liability.comparative_fault_allegation`, `liability.traffic_signal` | Prose; optional keyword flags only |
| `collision.impact_type`, `collision.airbags`, `collision.transport` | Often checkbox/narrative—add MVP rows when form patterns stabilize |
| `correspondence.requested_items`, `correspondence.missing_document` | List semantics |

Keyword **co-occurrence** detectors (e.g. fracture vs no fracture) may create **issues** without creating settled facts.

---

## 6. Conflict and gap policy

| Situation | Behavior |
|-----------|----------|
| Two normalized values for same critical `fact_type` | Keep both; IssueService `*.*_conflict`; status `conflicting` |
| Critical type missing after all docs | Red review / `create_gap_reviews` — do not fill |
| Low OCR confidence on critical span | Apply [03-ocr-thresholds](./03-ocr-thresholds.md) matrix → Amber/Red |
| Billing arithmetic mismatch | BillingService + `billing.*` issues — not parser invention |

---

## 7. Growth process

1. Fail a gold/eval must-find or see repeated Amber/Red.  
2. Add label synonym or tighten pattern under a new `parser_id` patch version (`v2`) if behavior changes.  
3. Update this catalog changelog; keep contracts `fact_type` stable.  
4. Prefer firm-approved gold over illustrative sample for production eval.

---

## Changelog

| Version | Date | Change |
|---------|------|--------|
| `0.1-provisional` | 2026-07-18 | Initial MVP + deferred catalog (Pass 4) |

# Fact Type Catalog

**contracts_version:** `0.1`  
**Status:** `canonical_v0.1` — **additive** (new types may be added; do not silently rename)

Source: prototype Appendix A, normalized to dotted `fact_type` strings.

Use these values in `Fact.fact_type`. Criticality hints guide Amber/Red policy (not hard-coded in all cases).

**Implementers:** Deterministic label/pattern parsers for MVP types are catalogued in [`docs/modules/05-fact-parser-catalog.md`](../modules/05-fact-parser-catalog.md).

| fact_type | Domain | Criticality hint | Notes |
|-----------|--------|------------------|-------|
| `client.name` | Identity | critical | |
| `client.dob` | Identity | critical | |
| `client.address` | Identity | normal | |
| `client.pronouns` | Identity | critical | Draft hygiene |
| `attorney.name` | Identity | normal | |
| `insurer.name` | Claim | critical | |
| `insured.name` | Claim | critical | Defendant / insured driver |
| `adjuster.name` | Claim | normal | |
| `claim.number` | Claim | critical | |
| `policy.number` | Claim | critical | |
| `collision.date` | Collision | critical | DOL |
| `collision.time` | Collision | normal | |
| `collision.location` | Collision | critical | |
| `collision.vehicles` | Collision | normal | |
| `collision.impact_type` | Collision | normal | |
| `collision.airbags` | Collision | normal | |
| `collision.transport` | Collision | normal | EMS/transport |
| `liability.traffic_signal` | Liability | normal | |
| `liability.admission` | Liability | normal | |
| `liability.citation` | Liability | normal | |
| `liability.police_finding` | Liability | normal | |
| `liability.witness` | Liability | normal | |
| `liability.comparative_fault_allegation` | Liability | normal | |
| `medical.provider` | Medical encounter | normal | |
| `medical.visit_date` | Medical encounter | normal | |
| `medical.complaint` | Medical encounter | normal | |
| `medical.pain_score` | Medical encounter | normal | |
| `medical.exam_finding` | Medical encounter | normal | |
| `medical.diagnosis` | Medical encounter | critical | Cross-check conflicts |
| `medical.treatment` | Medical encounter | normal | |
| `medical.medication` | Medical encounter | normal | |
| `imaging.study_date` | Imaging | normal | |
| `imaging.modality` | Imaging | normal | |
| `imaging.level` | Imaging | normal | |
| `imaging.finding` | Imaging | critical | e.g. fracture vs none |
| `imaging.measurement` | Imaging | normal | |
| `imaging.stenosis` | Imaging | normal | |
| `imaging.fracture` | Imaging | critical | |
| `imaging.recommendation` | Imaging | normal | |
| `recovery.improvement` | Recovery | normal | |
| `recovery.resolved_symptoms` | Recovery | normal | |
| `recovery.discharge` | Recovery | normal | |
| `recovery.mmi` | Recovery | normal | |
| `recovery.restrictions` | Recovery | normal | |
| `recovery.future_care` | Recovery | normal | |
| `prior.preexisting_diagnosis` | Prior condition | critical | |
| `prior.prior_symptoms` | Prior condition | normal | |
| `prior.asymptomatic_status` | Prior condition | normal | |
| `prior.aggravation_opinion` | Prior condition | normal | |
| `damages.charge` | Damages | normal | Line-level; see BillingEntry |
| `damages.payment` | Damages | normal | |
| `damages.adjustment` | Damages | normal | |
| `damages.balance` | Damages | normal | |
| `damages.lien` | Damages | normal | |
| `damages.wage_loss` | Damages | normal | |
| `damages.out_of_pocket` | Damages | normal | |
| `damages.specials_claimed` | Damages | critical | User-confirmed when ambiguous |
| `correspondence.requested_items` | Correspondence | normal | |
| `correspondence.response_deadline` | Correspondence | normal | |
| `correspondence.offer_deadline` | Correspondence | critical | |
| `correspondence.missing_document` | Correspondence | normal | |
| `demand.authorized_amount` | Demand parameters | critical | User-supplied |
| `demand.multiplier` | Demand parameters | normal | If firm uses |
| `demand.offer_expiry` | Demand parameters | critical | |
| `demand.exhibit_order` | Demand parameters | normal | |

## Changelog

| Version | Change |
|---------|--------|
| 0.1 | Initial catalog from Appendix A |
| 0.1 | Link to module 05 fact parser catalog (Pass 4) |

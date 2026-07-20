# Phase 5 Firm Gold Review Preparation

**Status:** `PENDING FIRM REVIEW`  
**Date:** 2026-07-20  
**Branch:** `phase-05-gold-validation`

## Baseline

| Field | Value |
|-------|-------|
| Phase 5 implementation commit | `cab86da303ae4340729d56a68194b92c90c4dab1` |
| Phase 5 audit report commit | `816261d6770cfe29c3ea5128e481c9f89e407a12` |
| Phase 5 audit verdict | `PASS WITH GAPS` |
| Remaining blocker | OD-07 firm-approved gold incomplete |
| Review-pack schema | `phase05-firm-gold-review.v1` |

Cursor did **not** approve the gold set. Phase 5 remains **unsuitable** for the immutable tag `phase-05-audited-pass`. No Phase 6 work was started.

## What was prepared

A lawyer/paralegal review pack was generated from the local Git-ignored reference package (safe aliases only). Private outputs live under the Git-ignored directory:

`tmp/phase05/firm-gold-review/`

Committed tooling (no case data):

- [`scripts/generate_phase05_gold_review.py`](../../scripts/generate_phase05_gold_review.py)
- [`scripts/validate_phase05_gold_review.py`](../../scripts/validate_phase05_gold_review.py)
- [`scripts/phase05_gold_review_schema.json`](../../scripts/phase05_gold_review_schema.json)
- [`scripts/requirements-gold.txt`](../../scripts/requirements-gold.txt) (`openpyxl` tooling-only)
- [`backend/tests/unit/test_phase05_gold_validator.py`](../../backend/tests/unit/test_phase05_gold_validator.py)

## Safe aggregates

| Metric | Count |
|--------|------:|
| CSV review rows (complete population) | 361 |
| Critical rows (critical types + missing-critical issues) | 261 |
| Conflict rows | 160 |
| Missing-critical rows | 4 |
| Parser-sample rows (XLSX) | 25 |
| Fact types covered | 23 |
| Document aliases | 10 |
| Deterministic source-link self-check errors | 0 |
| Reviewer decision cells prefilled | 0 (all blank) |
| Sign-off prefilled | No |

Fact-type coverage (names only): attorney.name, calc.service_date_range, calc.visit_count, claim.number, client.address, client.dob, client.email, client.name, client.phone, client.pronouns, collision.date, collision.location, collision.report_number, correspondence.offer_deadline, damages.specials_claimed, imaging.study_date, insured.name, insurer.name, liability.citation, medical.diagnosis, medical.provider, medical.visit_date, policy.number.

## Self-validation / import-validator

| Check | Result |
|-------|--------|
| Pack self-check (`ok`) | PASS |
| Span ID integrity | PASS (0 errors) |
| Demand/template not primary-verified | PASS |
| Calculated facts carry input IDs | PASS |
| Draft XLSX validation (`--allow-unsigned`) | PASS |
| Draft CSV validation (`--allow-unsigned`) | PASS |
| Synthetic validator tests | **12 passed** |
| Malformed / unsigned / unresolved / hash-drift cases | Covered by unit tests |
| Git-ignore of private pack | PASS (`tmp/` rule) |

## Production regression

| Suite | Result |
|-------|--------|
| Backend pytest | **252 passed** (prior Phase 5 baseline 240 + 12 gold validator tests) |
| Frontend vitest | **12 passed** |
| Production build | PASS |
| Contract drift | none |
| `node scripts/check-all.mjs` | PASS |

## What to send the lawyer

**Send:**

`tmp/phase05/firm-gold-review/phase05_firm_gold_review.xlsx`

**Also useful (optional companion):**

`tmp/phase05/firm-gold-review/README.txt`

**Do not send to public AI services:** evidence PDFs/DOCX, private CSV, manifest, extraction snapshot, or context snippets.

## What the lawyer must return

**Return:** the same workbook file, completed:

`phase05_firm_gold_review.xlsx`

Requirements for a valid return:

- Sheet names unchanged
- Rows not deleted
- Reviewer decisions filled for critical/conflict work
- False-negative facts added only on **Missing Facts**
- **Sign-off** completed (name, approval status, primary-evidence confirmation, demand-not-SoT confirmation)

After return, validate locally (does not import into production facts):

```text
python scripts/validate_phase05_gold_review.py ^
  --xlsx path\to\returned\phase05_firm_gold_review.xlsx ^
  --manifest tmp\phase05\firm-gold-review\phase05_firm_gold_manifest.json
```

(Omit `--allow-unsigned` for final acceptance.)

## Explicit statements

- Status: **`PENDING FIRM REVIEW`**
- Cursor did **not** approve this gold set
- Existing demand letters must **not** be treated as the factual answer key
- Phase 5 remains unsuitable for `phase-05-audited-pass` until firm gold is approved and a later honesty audit is performed
- No Phase 6 chronology/billing work was begun
- No audited-pass tag was created

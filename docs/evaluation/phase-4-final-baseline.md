# Phase 4 final baseline (consolidation)

Structured baseline for Phase 4 release evidence after Corrections 1–7.
Numeric fields that require live acceptance on the consolidation branch are
marked **Pending measurement on consolidation branch**. Do not invent CER
percentages, private filenames, or unverified durations.

Opaque private labels only (examples already used in prior docs):
`private_police_scan`, `private_billing_document`, `private_text_rich_097`,
`private_medical_embedded_ocr`.

## Prior evaluation references

| Document | Scope |
|----------|-------|
| [phase-4-printed-ocr-baseline.md](phase-4-printed-ocr-baseline.md) | Synthetic printed OCR CER/WER calibration |
| [phase-4.5-routing-performance-baseline.md](phase-4.5-routing-performance-baseline.md) | Hybrid routing / throughput (pre–Correction 1+ medical note) |
| [phase-4-dense-form-ocr-quality.md](phase-4-dense-form-ocr-quality.md) | Correction 5 quality gate eval plan |
| [phase-4-targeted-repair.md](phase-4-targeted-repair.md) | Correction 6 repair eval |
| [phase-4-fair-scheduling.md](phase-4-fair-scheduling.md) | Correction 7 fairness metrics |
| [phase-3-native-trust-baseline.md](phase-3-native-trust-baseline.md) | Native trust baseline |

## Runtime profile (record on measurement)

| Item | Value |
|------|-------|
| Branch / commit | Pending measurement on consolidation branch |
| Tag target | `phase-4-visual-detection-printed-ocr-v2` |
| OCR models (Settings default) | `PP-OCRv5_mobile_det` / `PP-OCRv5_mobile_rec` |
| `OCR_WORKERS` | 1 |
| Fair scheduling | Pending measurement on consolidation branch (`FAIR_OCR_SCHEDULING_ENABLED`) |
| Progress cap | 65% |
| Machine class | Pending measurement on consolidation branch |

---

## Police-style scan (`private_police_scan`)

| Field | Value |
|-------|-------|
| Pages | 2 (prior docs) |
| Expected / measured routes | Pending measurement on consolidation branch |
| Wall duration | Pending measurement on consolidation branch |
| Peak RSS | Pending measurement on consolidation branch |
| Overlay / box sanity | Pending measurement on consolidation branch |
| Progress / lifecycle | Pending measurement on consolidation branch |
| Pass | Pending measurement on consolidation branch |

Prior opaque note (pre-consolidation): full_visual_ocr ×2 observed on an
earlier Phase 4.5 tip — re-measure on consolidation; do not treat as final.

---

## Billing hybrid (`private_billing_document`)

| Field | Value |
|-------|-------|
| Pages | 9 (prior Correction 2 docs) |
| digital_native | Pending measurement on consolidation branch |
| full_visual_ocr / embedded / repair | Pending measurement on consolidation branch |
| Duplicate paths (A/B/none) | Pending measurement on consolidation branch |
| Final document policy | Pending measurement on consolidation branch |
| Wall duration | Pending measurement on consolidation branch |
| Pass | Pending measurement on consolidation branch |

Prior opaque Correction 2 tip (sanitised): digital_native ×7, full_visual_ocr ×2
— re-measure on consolidation.

---

## Text-rich 97-page (`private_text_rich_097`)

| Field | Value |
|-------|-------|
| Pages | 97 |
| digital_native | Pending measurement on consolidation branch |
| full_visual_ocr | Pending measurement on consolidation branch |
| Glyph quarantine warnings | Pending measurement on consolidation branch |
| Wall duration (routing-only / HTTP) | Pending measurement on consolidation branch |
| Final document policy | Pending measurement on consolidation branch |
| Pass | Pending measurement on consolidation branch |

Prior opaque Correction 3 tip (sanitised): digital_native ×97, full_visual_ocr ×0
— re-measure on consolidation.

---

## 104-page embedded / medical-style (`private_medical_embedded_ocr`)

| Field | Value |
|-------|-------|
| Pages | 104 |
| Native retained | Pending measurement on consolidation branch |
| Embedded OCR verified | Pending measurement on consolidation branch |
| Targeted repair | Pending measurement on consolidation branch |
| Full visual OCR | Pending measurement on consolidation branch |
| Average full-OCR page seconds | Pending measurement on consolidation branch |
| Wall duration | Pending measurement on consolidation branch |
| Peak RSS | Pending measurement on consolidation branch |
| Pass | Pending measurement on consolidation branch |

Prior Phase 4.5 tip measured full_visual_ocr ×104 before ADR 0031
verification-candidate retention — **must be re-measured** after Corrections
1–7; do not copy old percentages as final.

---

## Batch performance (fair scheduling)

Mixed batch including short OCR, large OCR, native-only, and hybrid documents.

| Metric | Value |
|--------|-------|
| Total batch duration | Pending measurement on consolidation branch |
| Time to first turn (small doc) | Pending measurement on consolidation branch |
| Time to first completed page (small doc) | Pending measurement on consolidation branch |
| Large-doc progress without starvation | Pending measurement on consolidation branch |
| Model reload count | Pending measurement on consolidation branch (expect 1 load) |
| Worker restart count | Pending measurement on consolidation branch |
| Pages processed twice | Pending measurement on consolidation branch (expect 0) |
| Pass | Pending measurement on consolidation branch |

Synthetic fairness workloads A–L are defined in
[phase-4-fair-scheduling.md](phase-4-fair-scheduling.md).

---

## Quality baselines (to be filled from acceptance runs)

| Corpus | Metric | Gate / note | Measured |
|--------|--------|-------------|----------|
| Synthetic printed OCR | Mean CER (clean) | See printed-ocr baseline suggested gates | to be filled from acceptance runs |
| Synthetic printed OCR | Mean CER (degraded) | See printed-ocr baseline | to be filled from acceptance runs |
| Dense-form synthetic | Primary vs fallback selection | Correction 5 | to be filled from acceptance runs |
| Targeted repair synthetic | Repair vs full-OCR fallback | Correction 6 | to be filled from acceptance runs |
| Private opaque cases | Route histogram only | No transcripts | to be filled from acceptance runs |

---

## Limitations (Phase 4)

- **Printed OCR is provisional** — calibration and opaque acceptance only; not
  firm-approved gold for legal accuracy.
- **Reading order is initial / geometric** — final reading order is Phase 7+.
- **Handwriting is not assessed** — `handwriting_assessment = pending_phase_5`.
- **No final table / form structure** — structure phases are later.
- Progress completes at **65%** maximum for this phase.
- Private corpora are local/gitignored; this document records aggregates only.

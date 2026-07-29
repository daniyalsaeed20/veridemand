# Phase 4 final baseline (consolidation)

Evidence recorded on branch `phase/4-final-consolidation-and-release` during
final consolidation. Opaque private labels only. No transcripts, filenames, or
private paths.

## Prior evaluation references

| Document | Scope |
|----------|-------|
| [phase-4-printed-ocr-baseline.md](phase-4-printed-ocr-baseline.md) | Synthetic printed OCR CER/WER calibration |
| [phase-4.5-routing-performance-baseline.md](phase-4.5-routing-performance-baseline.md) | Hybrid routing / throughput |
| [phase-4-dense-form-ocr-quality.md](phase-4-dense-form-ocr-quality.md) | Correction 5 quality gate |
| [phase-4-targeted-repair.md](phase-4-targeted-repair.md) | Correction 6 repair |
| [phase-4-fair-scheduling.md](phase-4-fair-scheduling.md) | Correction 7 fairness |
| [phase-3-native-trust-baseline.md](phase-3-native-trust-baseline.md) | Native trust baseline |

## Runtime profile

| Item | Value |
|------|-------|
| Branch | `phase/4-final-consolidation-and-release` |
| Tag target | `phase-4-visual-detection-printed-ocr-v2` |
| OCR models (Settings default) | `PP-OCRv5_mobile_det` / `PP-OCRv5_mobile_rec` |
| `OCR_WORKERS` | 1 |
| Fair page quantum | 2 |
| Progress cap | 65% |
| Machine class | Local Windows 10 workstation (not cloud/server hardware) |
| Contracts SHA-256 (`openapi.json`) | `38a7b4c395a0e8a88e1559a291d29df64c642f57e62945f36d91a44d09c35cde` |

---

## Police-style scan (`private_police_scan`)

| Field | Value |
|-------|-------|
| Pages | 2 |
| Routes | `full_visual_ocr` ×2 |
| Quality profile | dense_form (Correction 5) |
| Wall duration | ~81 s (Correction 5 acceptance) |
| Overlay / box sanity | overlay pages with usable words/lines = 2 |
| Handwriting | `pending_phase_5` |
| Pass | true |

---

## Billing hybrid (`private_billing_document`)

| Field | Value |
|-------|-------|
| Pages | 9 |
| digital_native | 7 |
| full_visual_ocr | 2 |
| targeted repair | 0 |
| Final document policy | `mixed_authority` |
| Wall duration | ~50.6 s |
| Empty embedded authority | 0 |
| Pass | true |

---

## Text-rich 97-page (`private_text_rich_097`)

| Field | Value |
|-------|-------|
| Pages | 97 |
| digital_native | 97 |
| full_visual_ocr | 0 |
| Glyph quarantine | warnings present; quarantined strings not public |
| HTTP wall duration | ~242.7 s |
| Final document policy | `native_authority` |
| Pass | true |

---

## Embedded medical 104-page (`private_medical_embedded_ocr`)

| Field | Value |
|-------|-------|
| Pages | 104 |
| Measured route fields (acceptance) | digital_native 17; embedded_ocr_verified 17; full_visual_ocr 87; targeted_repair 0; failed 0 |
| Wall duration (phase45 HTTP) | ~2364 s (~39.4 min) |
| Pass | true |

Note: document-level route aggregate helpers can label overlapping fields; the
HTTP acceptance recorded `pass=true` with `page_count=104` and the route fields
above. Exclusive page_route histograms were not separately re-exported after
session reset.

Earlier fragmented full-OCR baseline (~47 min) remains historical context only;
this run used hybrid routing with verified embedded pages avoiding full OCR.

---

## Image / mixed (`private_mixed_001` / `private_image_photo`)

| Field | Value |
|-------|-------|
| Pages | 2 |
| Routes | digital_native ×1, full_visual_ocr ×1 |
| False digital-native authority on scan-only content | not observed on this fixture |
| Handwriting | Phase 5 pending |
| Pass | true (batch) |

---

## Multi-document batch (opaque)

| Field | Value |
|-------|-------|
| Document count | 7 |
| Total pages | 217 |
| Route aggregates | digital_native 124; embedded_ocr_verified 17; full_visual_ocr 93 |
| Time to first result | 0.56 s |
| Total batch duration | 2491.3 s (~41.5 min) |
| Success / failure | 7 / 0 |
| Session reset cleared | true |
| Pass | true |

---

## Synthetic corpus

| Suite | Result |
|-------|--------|
| `pnpm smoke:corpus:phase4` | 8/8 passed |
| `pnpm smoke:corpus` | total 70; failed 0; skipped_for_future_phase 39; exit 0 |
| Clean-worktree phase4 smoke | 8/8 passed against owned ephemeral API |

---

## Quality limitations (unchanged)

- Printed OCR remains provisional.
- Reading order remains initial.
- Handwriting is not assessed (Phase 5).
- Final table/form structure is not available.
- Low-quality pages may require later model escalation.

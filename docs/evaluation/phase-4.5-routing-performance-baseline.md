# Phase 4.5 routing performance baseline

Sanitised comparison from local opaque corpus runs (no private filenames/text).

## Before (v1.5 behaviour, observed)

| Metric | Value |
|--------|-------|
| Pages evaluated (medical opaque) | 104 |
| Pages fully OCRed | 104 (document-level visual selection) |
| Average full-OCR page duration | ~25–35 s (operator observation pre-4.5) |
| Total document duration (projected) | ~50 minutes |
| Peak RSS | not captured in this release |
| Worker count | 1 |

## After (v1.6 hybrid routing) — measured 2026-07-27

| Metric | Value |
|--------|-------|
| Native retained (medical) | 0 |
| Embedded OCR verified (medical) | 0 |
| Targeted repair (medical) | 0 |
| Full OCR (medical) | 104 |
| Visual no text (medical) | 0 |
| Verification duration | n/a (no embedded candidates retained) |
| Full-OCR duration (medical wall) | 2818.7 s (~47.0 min) |
| Average full-OCR page seconds | 22.70 |
| Pages per minute | 2.64 |
| Worker count | 1 |
| Recognition batch size | settings default |
| Primary / fallback det side | 960 / 1600 |
| Fast-pass | enabled (primary then optional fallback) |

### Private subset (opaque)

| Label | Pages | Routes (measured) | Duration | Pass |
|-------|------:|-------------------|----------:|------|
| private_police_scan | 2 | full_visual_ocr ×2 | 46.2 s | yes |
| private_billing_digital | 1 | digital_native ×1 | 2.0 s | yes |
| private_medical_embedded_ocr | 104 | full_visual_ocr ×104 | 2818.7 s | yes |

Notes:

- Image dominance alone no longer forces OCR in code, but this medical PDF
  produced zero pages with a retained native/embedded layer after Phase 3 trust;
  measured route is therefore full visual OCR on every page.
- Billing digital retained native authority (full OCR skipped).
- Police scan remained full visual OCR on both pages.
- Handwriting remains `pending_phase_5`.
- Fair OCR scheduling remained disabled (`FAIR_OCR_SCHEDULING_ENABLED=false`).

Do not invent mandatory speed percentages beyond measured values.

# Billing Extraction Spike Report

**Status date:** 2026-07-19  
**Spike:** [`spikes/billing/`](../../spikes/billing/)  
**Source:** `docs/example/AMINI_MAYEL_20260706_eCW Billing Ledger.pdf` (1 page, landscape)  
**Raw metrics:** `spikes/billing/out/metrics.json`  
**Related OCR:** ledger page OCR mean conf ≈ 0.985 (`ocr-spike-report.md`)

---

## Executive finding

Native text on this eCW **Patient Transaction Report** is largely **unusable** (`(cid:N)` ratio ≈ **0.57**). Positioned geometry still exists. A few currency and left-column code tokens survive in the native layer; headers/descriptions do not. Reliable CPT/column assignment requires **OCR (or a different export)** plus layout-specific rules — not a generic one-shot parser.

---

## 1. Values correctly reconstructed (native layer)

| Item | Evidence |
|------|----------|
| Page geometry | 792×612 landscape; 172 words; 27 provisional Y-grouped rows |
| Currency tokens via `Decimal` | `$272.00`, `$363.00`, `$340.00`, `$295.00`, `$1,270.00`, `$1,918.00`, `($648.00)`, `$1,270.00` (duplicate) |
| Right-margin amount column heuristic | All 8 money tokens near `x0≈694–718` |
| Left-column numeric codes | `100522`, `106082`, `109492`, `109586` (6-digit) |
| Patient/report title fragments | `PatientTransaction`, `Report`, `AMINI,` readable |

OCR (separate spike) recovers readable headers such as “Patient Transaction Report”, provider filters, and denser line text — suitable as input to a later row parser.

---

## 2. Values requiring layout-specific rules

| Rule need | Why |
|-----------|-----|
| eCW landscape PatientTransaction layout | Not a simple 5-column CMS bill |
| OCR-first or cid-gate before column map | Headers are cid-garbled in native |
| 6-digit codes ≠ assume CPT-5 | Codes may be charge/transaction IDs until labels confirmed |
| Deduplicate echoed amounts | `$1,270.00` appears twice (line vs subtotal/balance risk) |
| Merge wrapped description rows | Y-tolerance grouping alone is insufficient after OCR |
| Parenthetical negatives as adjustments/payments | `($648.00)` parsed as −648.00 |

---

## 3. Values that should create review issues

| Issue intent | Trigger |
|--------------|---------|
| `extraction.broken_text_layer` | High cid ratio on native |
| `billing.layout_uncertain` (or equivalent) | Header-based column assignment failed natively |
| Manual ledger confirmation | Cannot assert printed total identity from unlabeled money tokens |
| **FR-BIL-04** specials confirmation | Must not infer legally claimed specials from this parse |
| Do not auto-verify OCR money/codes as gold | Pending firm gold + user confirm |

---

## 4. Values that cannot yet be determined

| Unknown | Notes |
|---------|-------|
| Whether 6-digit codes are CPT / internal IDs | Labels garbled until OCR+header map reviewed |
| Which money tokens are charges vs subtotals vs balances | Summing all tokens (`5080.00`) is **not** a verified total |
| Authoritative provider totals for Phase 6 gold | Missing from illustrative gold (`gold-readiness.md`) |
| Claimed specials (~$6783 demand cite) | `todo_verify` / user-supplied path |

Experimental reconciliation snapshot (native money tokens only):

| Metric | Value |
|--------|-------|
| Sum all money tokens | 5080.00 (invalid as ledger total) |
| Sum positives | 5728.00 |
| Sum negatives | −648.00 |

---

## Recommendation for Phase 6

1. Route this ledger class to OCR when cid ratio high.  
2. Build an **eCW PatientTransaction** adapter: header x-centers from OCR, row group, Decimal money, code column as opaque until labeled.  
3. Emit review issues whenever totals disagree or labels missing.  
4. Never invent specials; require FR-BIL-04 confirmation.

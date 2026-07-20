# Extraction Evaluation Metrics

**Status:** Remediation Part 1 — metric catalogue (proposals for thresholds live in the acceptance matrix)  
**Rule:** Metrics score extraction fidelity against **human-approved** annotations. Machine prefill is never ground truth. Dictionary correctness is **not** a sole measure (names, IDs, and medical codes may be non-lexical).

---

## 1. Annotation prerequisites

| Annotation status | Eligible for soft metrics? | Eligible for hard invariants? |
|-------------------|----------------------------|-------------------------------|
| `unreviewed` / `machine_prefill` | No (diagnostic only) | Structural checks only |
| `human_approved` | Yes | Yes |
| `disputed` / `unreadable` | Partial (safe-failure scoring) | Yes |

Unapproved annotations must be excluded from acceptance rollups.

---

## 2. Text metrics

Let \(R\) be reference text and \(H\) hypothesis text after agreed normalization (Unicode NFC, collapse whitespace for CER/WER unless exact-line mode).

| Metric | Definition |
|--------|------------|
| **CER** | Character Error Rate = \((S+D+I) / N\) where \(N\) = reference character count; requires character-level GT |
| **WER** | Word Error Rate = \((S+D+I) / W\) over whitespace-tokenized words |
| **Exact-line match rate** | Fraction of reference lines exactly equal to aligned hypothesis lines |
| **Word precision** | \(TP / (TP+FP)\) over bag or alignment of words |
| **Word recall** | \(TP / (TP+FN)\) |
| **Spurious-token rate** | \(FP / \max(1, |H|)\) |
| **Missing-token rate** | \(FN / \max(1, |R|)\) |
| **Single-character-fragment rate** | Fraction of hypothesis tokens with length 1 that are not in an approved singleton set (digits, punctuation allowed by annotation) |
| **Nonlexical / nonsense-token diagnostics** | Count of tokens failing a lightweight printable/structure check (not a dictionary reject of proper names) |
| **Duplicate-text-layer rate** | Fraction of pages where two layers contain near-duplicate streams without explicit dual-layer labelling |

CER is computed only when character GT exists; otherwise report `cer_unavailable`.

---

## 3. Reading-order metrics

| Metric | Definition |
|--------|------------|
| **Line-order agreement** | Kendall / pairwise agreement of line sequence IDs vs reference |
| **Word-order agreement** | Same for word sequence within page or region |
| **Pairwise order error** | Count of inverted pairs / total comparable pairs |
| **Cross-column merge count** | Tokens that jump columns relative to annotated column regions |
| **Cross-row merge count** | Table cells merged across rows incorrectly |
| **Header/body merge count** | Header tokens inserted into body sequence |
| **Footer/body merge count** | Footer tokens inserted into body sequence |
| **Table-cell ordering accuracy** | Fraction of annotated cells whose reading order index matches |
| **Label/value association accuracy** | Fraction of annotated label→value pairs correctly associated |

---

## 4. Geometry metrics

| Metric | Definition |
|--------|------------|
| **Valid polygon rate** | Fraction of polygons passing validity rules |
| **Out-of-bounds polygon rate** | Fraction with any vertex outside `[0,1]` (epsilon allowed) |
| **Box centre within expected region** | Fraction whose centroid lies in annotated region |
| **IoU** | Intersection-over-union vs manually annotated boxes (when present) |
| **Word-box visual alignment** | Pass/fail or mean IoU for word boxes |
| **Line-box visual alignment** | Same for line boxes |
| **Rotation correctness** | Declared rotation matches annotated display rotation |
| **Deskew inverse correctness** | After inverse transform, boxes align to display GT |
| **Viewer overlay alignment** | Manual or synthetic check that overlay matches selected text |
| **Cross-page / source mismatch rate** | Tokens referencing wrong page or document |

---

## 5. Layer-selection metrics

| Metric | Definition |
|--------|------------|
| **Corrupt embedded-text false-acceptance count** | Pages where corrupt embed was selected canonical |
| **Good native-text false-rejection count** | Pages where good native was rejected for OCR without cause |
| **Fresh-OCR unnecessary-run count** | Fresh OCR run when native was labelled trustworthy |
| **OCR-required page miss count** | Pages needing OCR but left on unusable native |
| **Canonical-layer selection accuracy** | Fraction matching annotated expected layer |
| **Silent mixing count** | Pages with unmarked native+OCR token mix |

---

## 6. Critical-field visual checks

Exact-match (after field-specific normalize) for annotated values such as:

- Person names  
- Law-firm names  
- Dates  
- Claim / policy / police report numbers  
- Badge / ID values  
- Monetary amounts (decimal-string compare)  
- Medical codes  

Each field records: expected, hypothesized, match boolean, layer used, box present, review status.

**Not scored here:** whether the value becomes an approved Fact entity.

User-confirmed anchors use status `USER_CONFIRMED_ANCHOR` and still require the page to be present.

---

## 7. Safe-failure metrics

| Metric | Definition |
|--------|------------|
| **Safe-failure rate** | Fraction of pages with correct outcome label among `{faithful, warnings, ambiguous, unreadable, unsupported}` |
| **Unsafe-usable count** | Pages labelled usable despite unreadable/disputed critical content |
| **Review-required coverage** | Disputed critical fields that are explicitly flagged |

---

## 8. Aggregates

Produce:

- Per-document-class aggregates  
- Per-engine aggregates  
- Per-page diagnostic reports (private)  
- Safe redacted summaries (committed reports: counts and rates only)

Private values, hashes, and excerpts must not appear in committed reports.

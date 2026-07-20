# Extraction Acceptance Matrix

**Status:** Remediation Part 1 — gate matrix  
**Provisional thresholds:** proposals only (require user approval — OD-17). Not product promises.

Exit status values: `not_evaluated` | `failed` | `conditionally_accepted` | `accepted`

GPT-assisted interpretation: **not permitted** for Part 1 scoring. Later permission is tracked per row; default **no**.

---

## 1. Document-class provisional bands (proposals)

| Document class | Metrics that matter | Suggested provisional thresholds (proposal) | Hard safety | Review mandatory when | User approval still required? |
|----------------|---------------------|-----------------------------------------------|-------------|----------------------|-------------------------------|
| Clean native PDFs | WER, order, geometry, layer | WER ≤ 0.02; order pairwise error ≤ 0.02; layer accuracy 100% | All invariants | Any critical mismatch | Yes |
| Good hidden-OCR scans | WER, layer (accept embed or fresh), geometry | WER ≤ 0.05; no silent mix | Invariants + no silent mix | Layer dispute | Yes |
| Corrupt hidden-OCR scans | Layer selection, safe failure, critical fields | Corrupt false-accept = 0; review_required on disputed | Zero corrupt accept | Always until layer correct | Yes |
| Image-only typed scans | Fresh OCR WER, geometry | WER ≤ 0.08 proposal | Invariants | Low conf / blank | Yes |
| Handwritten forms | Safe failure, critical exact, order | Prefer review_required over wrong accept | Zero uncertain critical accept | Default for disputed glyphs | Yes |
| Mixed print/hand | Layer + field exact + safe failure | Class-specific | Invariants | Hand regions | Yes |
| Tables / billing ledgers | Table order, label/value, geometry | Cell order ≥ 0.90 proposal | No fabricated cells | Cell ambiguity | Yes (also OD-14) |
| DOCX-derived PDFs | Text + order + viewer align | WER ≤ 0.02 | Invariants | Conversion artifacts | Yes |
| Rotated / skewed pages | Rotation, deskew inverse, geometry | Rotation correct 100%; IoU ≥ 0.5 where annotated | Invariants | Failed deskew | Yes |
| Diagrams with incidental text | Unsupported vs extract | Explicit unsupported or region-scoped | No body pollution | Diagram text | Yes |

---

## 2. Capability matrix

| Capability | Required test pages | Required annotations | Required metrics | Hard invariants | Provisional threshold | Mandatory manual checks | Failure handling | GPT later? | Exit status |
|------------|---------------------|----------------------|------------------|-----------------|----------------------|-------------------------|------------------|------------|-------------|
| Text fidelity | Native + OCR classes | Approved transcript | CER (if avail), WER, P/R | No fabricated text | Per class band | Spot-check pages | Queue review; do not claim accept | No | `not_evaluated` |
| Word fidelity | Word-level native; OCR line-derived flagged | Word list / order | Word P/R, fragment rate | No fabricated word boxes | Per class | Overlay spot-check | Flag derived words | No | `not_evaluated` |
| Character fidelity | Only if char GT + engine support | Char boxes | CER, char IoU | No fabricated char boxes | N/A until OD-18 | N/A | Capability off | No | `not_evaluated` |
| Reading order | Two-column, table, header/footer | Order indices + regions | Order metrics | — | Per class | Column/table visual | Mark order fail | No | `not_evaluated` |
| Table structure | Billing + synthetic table | Cell grid | Cell ordering | No invented cells | Proposal ≥ 0.90 | Ledger spot-check | Review / unsupported | No | `not_evaluated` |
| Form label/value | Form + police-like | Label/value pairs | Association accuracy | — | Proposal ≥ 0.90 | Field spot-check | Review | No | `not_evaluated` |
| Handwriting | Handwritten / mixed | Unreadable markers + critical | Safe failure, field exact | Uncertain → review | Prefer fail-closed | Always | `unreadable_review_required` | No | `not_evaluated` |
| Geometry | All selected pages | Boxes or regions | Valid/OOB/IoU | Zero invalid canonical | Valid ≥ 0.99; OOB = 0 | Overlay | Reject page/engine claim | No | `not_evaluated` |
| Layer selection | Corrupt embed + clean native + image-only | Expected layer | Layer metrics | Zero silent mix; zero corrupt accept | 100% on labelled set | Native trustworthiness Q | Fail gate | No | `not_evaluated` |
| Viewer alignment | Synthetic + sample real | Boxes | Overlay alignment | Boxes match selected text | Pass manual | Highlight check | Fail geometry | No | `not_evaluated` |
| Critical-field exactness | Pages with anchors | Exact expected values | Exact match | Zero uncertain accept | 100% on approved anchors | Visual confirm | Review required | No | `not_evaluated` |
| Safe failure | Unreadable / corrupt samples | Outcome labels | Safe-failure metrics | No unsafe-usable | 100% labelled outcomes | Outcome audit | Fail gate | No | `not_evaluated` |

---

## 3. Remediation Part 1 exit gate

Part 1 is complete when:

- [x] Acceptance contract exists  
- [x] Metrics defined and implemented in tooling  
- [x] Vendor-neutral evaluation schema exists  
- [x] Safe synthetic fixtures exist  
- [x] Private real-corpus manifest exists  
- [x] Representative pages selected  
- [x] Known anchors represented where files available  
- [x] Annotation/review tooling works  
- [x] Baseline current-system measurements generated  
- [x] Private files remain ignored  
- [x] Safe reports contain no confidential values  
- [x] No production extraction code changed  
- [x] No OCR engine decision made prematurely  

If real annotations remain unreviewed:

**`CORPUS REVIEW TOOL READY — HUMAN REVIEW PENDING`**

(Earlier phrasing `CORPUS PREPARED — HUMAN GROUND-TRUTH REVIEW PENDING` still applies to gold status: the corpus is **not** gold until human-checked.)

Difficult police report with badge/ID corrupt-embed challenge: present in the private multi-case corpus (deduplicated); human review via the localhost app remains required.

Do not call the entire corpus gold during tooling delivery.

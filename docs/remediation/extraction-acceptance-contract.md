# Extraction Acceptance Contract

**Status:** Remediation Part 1 — measurement contract (not a production API change)  
**Audience:** Extraction evaluation, OCR/engine comparisons, human page review  
**Rule:** This document defines *how source extraction quality is measured*. It does not authorize changing production extraction code, OCR vendors, routing, or `SourceToken` / `SourceSpan` contracts.

---

## 1. Purpose

VeriDemand must prove that page text, reading order, geometry, and layer selection are faithful to the **visible page** before any engine swap, routing change, or parser repair is accepted.

Critical-field checks in this contract measure **extraction fidelity only** (visible text match). They are **not** semantic fact approval and do not unlock Phase 5 gold claims.

---

## 2. Page identity and provenance

Every canonical extraction item (page result, region, line, word, optional symbol) must carry enough provenance to reproduce and audit the result:

| Field | Required | Notes |
|-------|----------|--------|
| Session / document ID | Yes (eval context) | Synthetic fixtures may use fixed IDs |
| Original file identifier | Yes | Private corpus: safe alias + private hash offline |
| Canonical viewing file | Yes when distinct | e.g. DOCX → PDF viewing copy |
| Page number | Yes | 1-based |
| Page dimensions | Yes | Media/crop box in PDF points or raster pixels |
| Page rotation | Yes | Effective display rotation |
| Render dimensions | Yes when OCR/render used | Bitmap width/height used for OCR |
| Extraction engine | Yes | Neutral name (`pdfplumber`, `paddleocr`, future engines) |
| Engine / model version | Yes | Must be declared; missing version fails scoring metadata gate |
| Extraction method | Yes | See input layers |
| Processing configuration | Yes | DPI, preprocess flags, language, thresholds version |
| Input layer | Yes | See §5 |

### Input layers

| Layer | Meaning |
|-------|---------|
| `native_pdf_text` | Embedded PDF text operators (true digital text) |
| `embedded_ocr` | Hidden/scanned text layer already inside the PDF |
| `fresh_ocr` | Newly rendered page OCR from an image |
| `manual_correction` | Human-edited transcript or boxes |
| `model_assisted_review` | Human-accepted suggestion from a model assist (future; not Part 1 production) |

Engines must not silently relabel `embedded_ocr` as `native_pdf_text`.

---

## 3. Text hierarchy

```text
document
→ page
→ layout region
→ line
→ word
→ symbol/character   (only when genuinely supported)
```

| Level | Mandatory for acceptance scoring? | Fabrication |
|-------|-----------------------------------|-------------|
| Document / page | Yes | Never invent pages |
| Layout region | Recommended; optional if whole-page region used | Do not invent table cells without evidence |
| Line | Yes for order metrics | May derive lines from words when engine is word-level |
| Word | Yes for word metrics | Do not invent words not supported by the engine output |
| Symbol / character | **Optional capability** | **Forbidden** unless genuine char/symbol geometry exists |

### Engine representation rules

- **Line-box-only OCR** (e.g. current PaddleOCR path): store lines as first-class units; words may be absent or derived for evaluation only and must be flagged `derived=true` (not claimed as engine geometry).
- **Word boxes:** preferred when the engine returns them; native pdfplumber words satisfy word-level geometry.
- **Symbol boxes:** allowed only when the engine returns them; character-level claims are **out of scope** for Part 1 firm requirements (see OD-18).

---

## 4. Geometry

| Rule | Requirement |
|------|-------------|
| Origin | Top-left of the **displayed** page |
| Normalized range | Coordinates in `[0, 1]` relative to displayed page width/height |
| Polygon | Closed quad or n-gon; reject empty / NaN / infinite |
| Page rotation | Geometry must match the same rotation used for viewing |
| Crop offsets | CropBox / render crop must be applied before normalization |
| Deskew inverse | If preprocess deskews, canonical boxes must map back to display space |
| Render scaling | OCR pixel boxes → normalized via render width/height |
| PDF viewer scaling | Overlay transforms must use the same normalized space as tokens |
| Box validity | `0 ≤ x,y ≤ 1`; min area; non-crossed edges |
| Box-to-visible-text | Boxes must enclose the selected visible glyphs, not an alternate layer |
| Alternate layers | Each layer keeps its own geometry; never overwrite rejected-layer boxes onto the canonical layer |

---

## 5. Reading order

Expected order (human reading order of the **visible** page):

| Layout | Expectation |
|--------|-------------|
| Normal paragraphs | Top-to-bottom, left-to-right within lines |
| Multi-column | Finish column N before column N+1; no cross-column snake |
| Tables | Cell-aware: row-major or documented reading path; no header/body merge |
| Forms | Label before/associated with its value; do not merge distant fields |
| Headers / footers | Separable from body; do not insert mid-paragraph |
| Rotated text | Order follows visual baseline after rotation normalization |
| Marginal text | May be separate regions; do not splice into body mid-sentence |
| Diagrams with text | Labels stay with diagram region; incidental text may be `unsupported` |
| Handwriting | Order follows visual lines; unreadable zones must be marked review |

---

## 6. Extraction-layer separation

Preserve separately (never silently merge):

1. Original embedded / native text result  
2. Fresh OCR result (when run)  
3. Selected **canonical** result  
4. Rejected result(s)  
5. Alternative candidate readings  
6. Selection reason  
7. Quality diagnostics  

**Hard rule:** Never concatenate or interleave `embedded_ocr` tokens with `fresh_ocr` tokens into one unmarked stream.

---

## 7. Safe failure outcomes

Every page or scored region must end in exactly one of:

| Outcome | Meaning |
|---------|---------|
| `faithful_canonical` | Extracted and selected as canonical without material doubt |
| `extracted_with_warnings` | Usable but diagnostics warn (low conf, partial coverage) |
| `ambiguous_with_alternatives` | Multiple plausible readings retained |
| `unreadable_review_required` | Human must review; no silent “usable” |
| `unsupported` | Layout/content class not supported for automated extraction |

A page must **not** be labelled usable merely because it contains many printable tokens.

---

## 8. Hard safety invariants

Independent of soft accuracy bands, acceptance requires:

1. **100%** of canonical words link to a valid page and region.  
2. **Zero** cross-session or cross-document source references.  
3. **Zero** silently fabricated word or character boxes.  
4. **Zero** canonical tokens from rejected extraction layers.  
5. **Zero** silent mixing of native and OCR text.  
6. **Zero** invalid / out-of-page canonical polygons.  
7. **Zero** accepted critical values when the visible reading remains materially uncertain.  
8. **Zero** accepted corrupt hidden-OCR pages in the labelled acceptance corpus (must be flagged).  
9. Every unreadable or disputed critical field is explicitly `review_required`.  
10. Bounding boxes highlight the **actual selected** visible text.  
11. Character-level claims are forbidden unless genuine character/symbol geometry exists.

Do not invent broad marketing accuracy claims (e.g. “99% accurate”).

---

## 9. Failure category separation

Score independently:

| Category | Examples |
|----------|----------|
| Text extraction failure | Wrong/missing glyphs relative to visible page |
| Reading-order failure | Columns/tables scrambled |
| Geometry failure | Misaligned or OOB boxes |
| Layer-selection failure | Corrupt embed accepted as native |
| OCR-recognition failure | Fresh OCR misreads visible text |
| Semantic parser failure | Correct text, wrong fact/role (out of scope for this contract) |
| Presentation failure | UI/workbook display clutter |

Parser bugs (e.g. `Patient` substring matches) are **not** OCR failures.

---

## 10. Relation to production contracts

Production `SourceToken` / `SourceSpan` remain unchanged in Remediation Part 1.  
The evaluation schema under `docs/remediation/schemas/` is labelled:

**EVALUATION SCHEMA — NOT YET PRODUCTION CONTRACT**

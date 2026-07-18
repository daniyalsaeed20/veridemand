# DOCX Template Spike Report

**Status date:** 2026-07-19  
**Spike:** [`spikes/docx-template/`](../../spikes/docx-template/)  
**Style reference (not evidence):** `Demand Mayel  Amini Final.docx` (note double space in filename)  
**Artifacts:** `spikes/docx-template/out/jackman_like_demand_template.docx`, `dummy_demand_rendered.docx`, `metrics.json`

---

## What was generated

Dummy demand via **docxtpl** containing:

- Header (firm name/address) + footer note  
- RE block (claim, client, DOL)  
- Multiple treatment-provider sections (`{%p for provider in providers %}`)  
- Specials table + parallel specials list  
- Settlement proposal (amount left as `[SETTLEMENT AMOUNT - TBD]`)  
- Closing + signature  
- Exhibit list  
- Filler blocks forcing multi-page body (~14k characters, 60 paragraphs post-render)

---

## Style-source inspection (Jackman demand)

| Metric | Value |
|--------|-------|
| Paragraphs | 66 |
| Tables | 2 |
| Sections | 1 |
| Header content detected | false (letterhead may be inline body, not header part) |
| Footer content detected | true |
| Fonts via python-docx | empty list (fonts may be theme/default not on runs) |
| Alignment mix | Centered letterhead-like lines + justified body |

---

## Formatting fidelity evaluation

| Concern | Spike result | Limitation |
|---------|--------------|------------|
| Headers | Present in template section header | Not a clone of firm logo/letterhead art |
| Footers | Present | True Word PAGE fields not injected |
| Tables | 1 table in rendered doc + paragraph specials loop | Avoided fragile `{%tr%}`-only specials path |
| Page breaks / multi-page | Long filler intended to paginate | Confirm in Microsoft Word / LibreOffice manually |
| Fonts | Forced Times New Roman in template | Firm face may differ; source fonts_seen empty |
| Spacing | Single spacing, 1″ margins | Not pixel-identical to firm DOCX |
| Repeated sections | Provider + exhibit Jinja loops OK | — |

**Manual gate still required:** open `dummy_demand_rendered.docx` in Word to confirm WYSIWYG. python-docx cannot fully certify Word layout.

---

## Feasibility verdict

| Question | Answer |
|----------|--------|
| Can docxtpl produce a multi-section Jackman-like demand shell? | **Yes** |
| Ready to promote spike template into production architecture? | **No** — needs letterhead/assets review, PAGE fields, firm style QA |
| Blocks Phase 0? | **No** |
| Informs Phase 8? | **Yes** — prefer template-first assembly (OD-09) |

---

## Recommendations

1. Derive production `jackman_demand_v1.docx` template under firm control (placeholders only; no matter PII).  
2. Keep specials as docxtpl-friendly tables with validated row loops after Word QA.  
3. Preserve TBD settlement as placeholder for preflight tests (`draft.placeholder`).  
4. Do not treat uploaded completed demands as evidence (FR-CLS-06).

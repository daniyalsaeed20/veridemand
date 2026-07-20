# Extraction Requirements Traceability

**Status:** Remediation Part 1 — read-only inventory  
**Rule:** Maps current requirements to code, tests, evidence, gaps, and **acceptance measurement**. Does not change production code.

| Requirement | Existing code | Existing tests | Existing evidence | Missing evidence | Proposed acceptance measurement |
|-------------|---------------|----------------|-------------------|------------------|----------------------------------|
| FR-EXT-01 native words + geometry | `backend/app/services/extraction/native.py`, `coordinates.py` | `test_native_extraction.py`, `test_coordinates.py` | Phase 2 reports; forensic page dumps | Character retention not in production SoT | Word WER/P/R + geometry validity/IoU on approved pages |
| FR-EXT-01 characters | Spec only; no char persistence | Name implies chars; tests cover words | Forensic `native_chars.json` (investigation only) | Production char boxes | CER only when char GT + capability approved (OD-18) |
| FR-EXT-02 native usability / route | `routing.py` | `test_native_routing.py`, `test_native_usability_gate.py` | Phase 3 thresholds doc; OD-01 | Measured thresholds on labelled corpus | Layer-selection metrics + routing baseline dump |
| FR-EXT-03 render via pypdfium2 | `ocr_page.py` + pdfium adapter | `test_phase03_ocr.py`, pdfium tests | Phase 3 reports | Per-page render meta in acceptance packs | Provenance fields + geometry after render scale |
| FR-EXT-04 preprocess retry | `preprocess.py`, `ocr_page.py` | `test_ocr_under_detection.py` | Phase 3 hardening | Deskew inverse on real corpus | Deskew inverse + rotation metrics |
| FR-EXT-05 PaddleOCR polygons/conf | `ocr/adapter.py`, `ocr_page.py` | `test_ocr_adapter.py`, `test_ocr_coordinates_quality.py` | OCR spike; Phase 3 | Word-level OCR boxes (line-only today) | Line-box alignment; derived-word flag; WER on fresh OCR |
| FR-EXT-06 unified token/span | `spans.py`, SourceToken/Span models | `test_span_grouping.py`, contract tests | Phase 2/3 | Line vs word granularity parity | Schema + source-link validity; no silent mix |
| FR-EXT-07 page warnings / unreadable | routing + ocr_quality + issues | OCR quality / blank tests | Phase 3 | Labelled safe-failure corpus | Safe-failure outcome accuracy |
| Doctrine §7.3 coords `[0,1]` top-left | `coordinates.py`, `geometry.py` | `test_coordinates.py` | Contracts | Viewer overlay visual corpus | Valid/OOB + overlay review questions |
| Doctrine §9.1 native→OCR route | `routing.py`, `process/service.py` | routing + phase03 integration | Thresholds doc | Corrupt-embed labelled set | Corrupt false-accept = 0 |
| Source spans for facts | Phase 5 fact service | Phase 5 unit tests | Phase 5 audit (gold gap) | Trustworthy extraction first | **Out of scope** for Part 1 scoring (parser separate) |
| Table / column model | Span gap split only (`spans.py`) | Distant-column split test | Billing spike; OD-14 | True table GT | Table-cell order metrics on synthetic + ledger pages |
| No LLM-first extraction | Process path has no LLM extract | Import/boundary culture | Doctrine / OD-12 | — | Eval schema forbids GPT as required engine |
| Critical visible anchors | — | — | User-confirmed names/firm; badge file gap | Human GT review; difficult police intake | Critical-field exact match + USER_CONFIRMED_ANCHOR |

## Known current limitations (measurement targets, not repairs)

1. Native path uses pdfplumber **words** only.  
2. OCR path stores PaddleOCR **line** detections as tokens.  
3. Character coordinates are not production SoT.  
4. Reading order lacks a proper table/column model.  
5. Corrupt embedded OCR can be mistaken for usable native text.  
6. Phase 5 facts are paused and must not be treated as trusted extraction output.

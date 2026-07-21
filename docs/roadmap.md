## Recommended Development Roadmap

VeriDemand should be developed through **10 phases, numbered Phase 0 through Phase 9**. This preserves the modular boundaries in the source-of-truth document and ensures Cursor completes, tests, and freezes one working increment before moving to the next. 

### Phase 0 — Repository Foundation and Contracts

Establish the new VeriDemand codebase and completely remove the previous demand-letter scope.

This phase creates:

- Monorepo structure.
- React/Vite frontend.
- FastAPI backend.
- Environment configuration.
- Pydantic API contracts.
- Generated OpenAPI, TypeScript and Zod schemas.
- Health and readiness endpoints.
- Linting, type-checking and test commands.
- Basic application shell and UI theme.

**Working result:** Both applications start successfully, the frontend communicates with the backend, contracts are generated consistently, and no demand-letter code remains.

FastAPI officially supports structuring larger applications across multiple modules, while Vite provides first-class React and TypeScript project scaffolding. ([FastAPI](https://fastapi.tiangolo.com/tutorial/bigger-applications/?utm_source=chatgpt.com))

---



### Phase 1 — Runtime Sessions, Uploads and Processing Queue

Build the temporary session workspace and multi-document upload flow.

This phase covers:

- Runtime-only sessions.
- Temporary session directories.
- Bulk file upload.
- File type, size, MIME and signature validation.
- Session limits.
- In-memory processing queue.
- Processing coordinator skeleton.
- Server-Sent Events progress stream.
- Queue dashboard UI.
- File removal, cancellation and session reset.
- TTL-based cleanup.

**Working result:** Users can upload several files, see them in a queue, receive live progress events and reset the entire temporary session. No extraction is performed yet.

---



### Phase 2 — Canonical Documents, Viewer and Coordinates

Ensure every supported document can be displayed using one reliable visual representation.

This phase implements:

- PDF.js viewer.
- PDF display.
- DOC and DOCX conversion through LibreOffice.
- Deterministic TXT-to-PDF conversion.
- Image and multipage TIFF handling.
- Canonical page dimensions.
- Normalised polygon and bounding-box contracts.
- Viewer zoom, rotation, fit-page and fit-width.
- Bounding-box overlay proof of concept.

**Working result:** Every supported file type can be opened in the viewer, and a test bounding box stays correctly aligned while zooming, resizing and rotating.

---



### Phase 3 — Native PDF Extraction and Trust Gate

Extract native PDF text where it is trustworthy and reject misleading text layers.

This phase implements:

- PDF inspection with `pypdf`.
- Word and character extraction with `pdfplumber`.
- Native coordinates.
- Unicode and geometry validation.
- Native-text trust scoring.
- Page-level source-authority decisions.
- Whole-document visual-authority escalation.
- Diagnostic warnings.
- Regression tests for `3936314.pdf` and corrupt billing documents.

**Working result:** Good digital PDFs use their native text, while bad or misleading PDF layers are automatically rejected and never appear as accepted output.

---



### Phase 4 — Visual Detection and Printed OCR

Process scanned pages and other visually authoritative printed documents.

This phase implements:

- Page rendering with `pypdfium2`.
- Conservative preprocessing.
- PaddleOCR text detection.
- PP-OCR printed-text recognition.
- Line and word coordinates.
- Basic layout grouping.
- Initial reading order.
- Page-by-page progress.
- Memory and resource cleanup.

**Working result:** Scanned printed documents produce selectable text with page locations and bounding boxes. Long documents process without freezing the UI or loading every page into memory.

PaddleOCR’s current architecture keeps text detection, recognition and document-structure components modular, which matches the separation required by VeriDemand. ([paddlepaddle.github.io](https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5.html?utm_source=chatgpt.com))

---



### Phase 5 — Handwriting Detection and Routing

Determine whether each visual text region is printed, handwritten, uncertain or non-text.

This phase covers:

- Region crop dataset preparation.
- Project-specific labelling.
- Lightweight image classifier.
- ONNX model export.
- ONNX Runtime inference.
- Classification thresholds.
- Printed, handwritten, uncertain and non-text routing.
- Routing evaluation report.
- False-positive and false-negative analysis.

**Working result:** Clearly printed regions are routed to local OCR. Handwritten and uncertain regions bypass local recognition and are reserved for the vision provider.

This phase classifies writing style only; it does not attempt local handwriting transcription.

---



### Phase 6 — Vision-LLM Transcription

Transcribe handwritten and uncertain visual regions through a configurable vision-model provider.

This phase implements:

- Provider-independent vision interface.
- OpenAI Responses API adapter.
- Region crop batching.
- Numbered contact sheets.
- Structured response schemas.
- Region-ID validation and merging.
- Retry, timeout and rate-limit handling.
- Partial-result behaviour.
- Legibility and ambiguity reporting.
- Mocked API tests.
- Controlled live evaluation.
- Regression test for the visible badge value `9065`.

**Working result:** Handwritten text is returned against detector-owned coordinates. Illegible content is reported honestly rather than guessed, and provider failure does not destroy valid native or OCR results.

`gpt-4.1-mini` remains available with image input and Structured Outputs, but current OpenAI guidance recommends newer model families for new complex workloads. Therefore, the implementation should retain `gpt-4.1-mini` as the specification default while making the provider and model configurable and benchmarking alternatives before locking the production model. ([OpenAI Developers](https://developers.openai.com/api/docs/models/gpt-4.1-mini?utm_source=chatgpt.com))

---



### Phase 7 — Structure, Tables, Search and Exports

Transform raw extraction output into complete document structure.

This phase implements:

- Pages, blocks, lines and words.
- Reading-order reconstruction.
- Headings, paragraphs, lists, headers and footers.
- Table, row, column and cell structure.
- Form and key-value spatial relationships.
- Search API.
- Search-result navigation.
- JSON export.
- Plain-text export.
- Markdown export.
- Result validation.

**Working result:** Every completed document has a valid structured result. Search opens the correct page and highlights the matching location. Tables are either reconstructed or clearly marked as unstructured.

---



### Phase 8 — Complete Frontend Workspace

Finish the user-facing experience after the extraction pipeline is functioning.

This phase implements:

- Polished upload and queue screen.
- Processing dashboard.
- Three-panel document workspace.
- Document and page navigation.
- Page thumbnails.
- Bidirectional text-to-box and box-to-text navigation.
- Search interface.
- Extraction-method filters.
- Warning and source-authority information.
- Cancellation and retry controls.
- Export controls.
- Responsive desktop and smaller-screen layouts.
- Loading, empty, failure and session-expired states.
- Accessibility and usability improvements.

**Working result:** A non-technical user can upload documents, follow progress, open completed files while others continue processing, inspect extracted text and download results without using developer tools.

---



### Phase 9 — Corpus Evaluation, Security and Hardening

Prove that the complete platform works against the real VeriDemand document corpus.

This phase covers:

- Gold-standard dataset.
- Character and word error measurements.
- Exact-value accuracy.
- Word-box coverage and IoU.
- Reading-order accuracy.
- Native-layer rejection accuracy.
- Handwriting-routing accuracy.
- Silent-error measurement.
- Full regression suite.
- Performance and memory benchmarking.
- File-security testing.
- Session-cleanup verification.
- Dependency and licence inventory.
- Reproducible model checksums.
- Production build and release checklist.

**Working result:** Known failure documents no longer return silent incorrect results, acceptance criteria pass, temporary files are reliably deleted, and the codebase is suitable as the foundation for future functionality.

---


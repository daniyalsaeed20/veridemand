# extraction (Phase 3+)

Reserved for the document-extraction pipeline. The subdirectories mark the
intended module boundaries; none are implemented in Phase 0:

- `native/` — native PDF text extraction and the trust gate (Phase 3).
- `rendering/` — page rendering to images (Phase 4).
- `layout/` — layout grouping (Phase 4).
- `printed_ocr/` — printed-text OCR (Phase 4).
- `handwriting_router/` — printed/handwritten/uncertain routing (Phase 5).
- `vision/` — vision-LLM transcription of routed regions (Phase 6).
- `reading_order/` — reading-order reconstruction (Phase 7).
- `validation/` — result validation and cross-checks (Phase 7).

No extraction libraries (pypdf, pdfplumber, pypdfium2, PaddleOCR, OpenCV,
Pillow, ONNX Runtime, OpenAI) are installed in Phase 0.

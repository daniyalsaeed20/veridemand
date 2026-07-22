# Phase 4 — Visual detection and printed OCR

## Scope

Phase 4 adds rendered-page visibility probing and **local printed OCR** on top
of Phase 3 native trust. Progress is capped at **65%**. Handwriting routing and
vision-LLM transcription are explicit Phase 5/6 boundaries.

## Flow

1. Canonical PDF ready; native trust completes (≤35%).
2. For accepted native pages: low-DPI visibility probe (ADR 0020).
3. Selected pages render one-at-a-time via pypdfium2 (DPI 200 for OCR).
4. Long-lived PaddleOCR worker runs PP-OCRv6 medium det/rec.
5. Coordinates map to normalised top-left `[0, 1]` space.
6. Geometric layout + provisional reading order published.
7. Per-page visual JSON published atomically; frontend fetches pages lazily.

## Module map

| Path | Role |
|------|------|
| `backend/app/extraction/visual/` | Renderer, visibility, paddle adapter, worker, service |
| `backend/app/extraction/rendering/` | Stub README → visual |
| `backend/app/extraction/printed_ocr/` | Stub README → visual |
| `backend/app/extraction/layout/` | Stub README → visual |

## Frontend

`VisualInspectionPanel` shows provisional OCR text and warnings.
`OcrOverlayLayer` draws line/word boxes with the same rotation transforms as
native overlays. Page results are fetched on demand (`useVisualPage`) — the
client does not store all-page OCR payloads.

## Related ADRs

0017–0021 under `docs/decisions/`.

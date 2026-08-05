# Phase 5 — Detector-first shadow pipeline

## Purpose

Task C0 separates Paddle text **detection** from text **recognition** behind an
explicit offline/shadow path so the handwriting router can eventually classify
detector-owned crops before printed recognition.

Target future runtime (not live in C0):

```text
page render → Paddle detection → ONNX writing-style router
  printed     → Paddle recognition
  handwritten → reserved_for_vision / pending_phase_6
  uncertain   → reserved_for_vision / pending_phase_6
  non_text    → suppress
```

C0 implements only:

```text
Paddle detection → stable regions/crops → separate Paddle recognition
```

The failed Task B–B4 classifiers are **not** used to control OCR.

## Live path (unchanged)

Phase 4 continues to use the combined `PaddleOCR.predict` pipeline in
`PaddleOcrAdapter.recognise`, loaded by the visual worker. Progress remains
capped at 65%. Fair scheduling, page routes, and route histograms are unchanged.
`HANDWRITING_ROUTER_ENABLED` remains false.

## Shadow / offline path

Setting (default off in all normal profiles):

```text
PHASE5_DETECT_FIRST_SHADOW_ENABLED=false
```

When false:

- no separate detector/recognizer modules are initialised by the worker;
- no additional page renders or crops;
- document results, progress, ETA, and route accounting are unchanged.

Separate modules are loaded only by explicit developer/acceptance commands via
`PaddleOcrAdapter.load_detect_first_modules()`.

## Adapter APIs

| Method | Behaviour |
|--------|-----------|
| `detect_text(page_image)` | PaddleX `create_model(det)` → `dt_polys` / `dt_scores` |
| `recognise_text_crops(crops)` | PaddleX `create_model(rec)` on supplied crops only |

Models: Settings defaults `PP-OCRv5_mobile_det` / `PP-OCRv5_mobile_rec`, reused
from the local `.models/paddleocr/` tree. Do not silently switch to PP-OCRv6.

Detection results carry stable region IDs, pixel + normalised geometry, and
detection confidence — **no recognised text**.

## Offline corpus

```text
pnpm phase5:detector-corpus:build
pnpm phase5:detector-corpus:compare
pnpm phase5:detector-corpus:coverage
```

Private artefacts: `fixtures/private/phase5/detector-first/` and
`detector-first-region-manifest.jsonl` (gitignored). Corpus version:
`phase5-detector-first-regions-v1`.

Every valid detection is retained before recognition, including empty / failed /
low-confidence / rejected recognition statuses.

## Related ADRs

- 0072 Separate Paddle detection and recognition
- 0073 Retain all detector regions before recognition
- 0074 Detector-first classifier crop contract
- 0075 Strict label-transfer rules
- 0076 Legacy path retained during shadow evaluation

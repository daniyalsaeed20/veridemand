# Combined PaddleOCR pipeline progress events

## Status

Accepted

## Context

VeriDemand invokes printed OCR through a single `PaddleOCR.predict(...)` call
in `backend/app/extraction/visual/paddle_adapter.py`. The underlying library does
not expose separately timed detection and recognition stage boundaries to the
application.

Earlier progress events labelled the combined call as `paddle_text_detection`
and sometimes emitted a second `started` status when the call returned.

## Decision

Public progress uses one honest operation:

- `paddle_ocr_pipeline` started
- `paddle_ocr_pipeline` heartbeat (optional, while the call runs)
- `paddle_ocr_pipeline` completed | failed | timed_out | cancelled

Separate `paddle_text_detection` / `paddle_text_recognition` labels are not
emitted unless VeriDemand later invokes detector and recogniser modules with
independently measured durations.

The ProcessingCoordinator is the sole owner of public progress transitions.
Worker NDJSON and the worker manager may carry diagnostic fields, but they must
not create duplicate public start events for the same operation attempt.

## Consequences

- Multipage overall progress maps page work into the 41–63 band and reaches 65
  only after summary publication and authority reconciliation.
- Frontend and logs show a single pipeline stage during Paddle inference.

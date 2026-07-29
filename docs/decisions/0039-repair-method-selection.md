# 0039 — Recognition-only versus local-detection repair

## Status

Accepted

## Context

Paddle recognition normally consumes detector crops. Some failures have trusted
geometry but wrong text; others have shifted or incomplete boxes.

## Decision

Support two explicit methods:

- `recognition_only` — crop known boxes and recognise without a detection stage.
- `local_detection_and_recognition` — detect+recognise inside the padded region
  crop only (never full-page detection through this route).

Allow one tested transition from recognition-only to local detection when the
first attempt yields no usable words. Otherwise fall back to full OCR.

## Consequences

Method, crop size, detector limit, batch size, duration, and result counts are
recorded as privacy-safe diagnostics.

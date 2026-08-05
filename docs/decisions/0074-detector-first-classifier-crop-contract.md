# ADR 0074 — Detector-first classifier crop contract

## Status

Accepted (Phase 5 Task C0)

## Context

A future handwriting router must train and infer on the same crop framing it
will receive at runtime. Mixed crop policies for printed vs handwriting would
bias the model.

## Decision

All detector-first crops use `phase5-crop-pad-v1` (8% of max source bbox side,
clamped to the page). Detector polygons remain authoritative; padding affects
the derivative crop only. Crops record SHA-256 of the PNG and of the page
render. No resize-to-classifier, augmentation, denoise, threshold, deskew,
transcription, or classification during corpus build.

## Consequences

Task C0 produces `phase5-detector-first-regions-v1` as the crop contract for
later router retraining. The legacy post-recognition crop corpus remains
unchanged and separate.

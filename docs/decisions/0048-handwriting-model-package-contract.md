# ADR 0048 — Handwriting classifier model package and preprocessing

## Status

Accepted (Phase 5 Task 2)

## Context

Phase 5 needs a reproducible, checksum-verified ONNX package and deterministic
crop preprocessing without OpenCV or geometry invention.

## Decision

Classifier packages live under a configured directory (default
`models/handwriting_classifier/`) containing `model.onnx`, `labels.json`,
`model-record.json`, and `metrics.json`. Manifests use strict Pydantic schemas
(`extra=forbid`). Labels are exactly `["printed","handwritten","non_text"]`.
Preprocessing is driven entirely by the manifest using Pillow and NumPy.
Package statuses include `test_fixture`, `evaluation_only`,
`production_candidate`, and `released`. `test_fixture` cannot satisfy
production-required readiness.

## Consequences

Verification is explicit (`scripts/verify_handwriting_classifier.py`). No
automatic model download on API startup. Production binaries are not committed
in Task 2; unit tests use a generated `test_fixture` under
`backend/tests/fixtures/handwriting_classifier/`.

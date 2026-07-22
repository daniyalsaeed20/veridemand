# Phase 3.2 — Document-specific native failure containment

**Date:** 2026-07-22  
**Branch:** `fix/phase-3-document-specific-native-failures`  
**Base tag (unchanged):** `phase-3-native-extraction-trust-gate-v1.1`  
**Corrective tag:** `phase-3-native-extraction-trust-gate-v1.2`

## Problem

Some multi-page documents failed the whole native stage with a generic
`NativeExtractionError: Native extraction worker failed`, while the canonical
PDF remained viewable. Parent logs lacked worker exception type, page, and
operation.

## Root-cause class

Uncaught content/parser exceptions outside the per-page extract try (and
insufficient worker diagnostics) caused document-wide exit code 1. Recoverable
malformed text layers must become page-level `error`/`rejected` +
`visual_authority`, not infrastructure failure.

## Fix

- Page-level try/except around metrics/trust/serialize; recoverable open errors
  become all-page visual errors with exit 0.
- Worker writes a privacy-safe failure envelope on true infrastructure failure;
  runner captures bounded stderr and envelope fields.
- Document summary exposes safe `failure_stage` / `failure_code` /
  `failure_message` / `failure_page_number` for the UI.

## Expected private outcomes (opaque)

| Label | Terminal stage | Policy |
|---|---|---|
| corrupt_layer_failure | native_trust_complete | visual_authority |
| mixed_native_failure | native_trust_complete | mixed_authority or visual_authority |

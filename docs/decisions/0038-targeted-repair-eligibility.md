# 0038 — Targeted-repair eligibility

## Status

Accepted

## Context

Limited local embedded-OCR failures should not force whole-page OCR, but repair
must only run when failures are spatially bounded and most of the page remains
trustworthy.

## Decision

Publish typed `TargetedRepairEligibilityEvidence` (`phase4-targeted-repair-v1`)
with centralised thresholds. A page is eligible only when a usable base result
exists, failed regions/count/coverage are within policy, retained candidate
coverage remains high, coordinates are valid, and repair is cheaper/safer than
full OCR. No filename, hash, or document-specific exceptions.

## Consequences

Ineligible pages route to full visual OCR. Eligible pages enter the targeted
repair pipeline once.

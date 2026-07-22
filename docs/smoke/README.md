# Synthetic PDF regression smoke corpus

## Purpose

This corpus is a **synthetic**, privacy-safe regression pack for VeriDemand’s
native-trust and canonical-viewer path. It is **test infrastructure**, not a
new product phase.

Triage reconciliation for the original 13 failures (baselines, classifications,
and skip integrity) lives in
[`phase-3-smoke-triage.md`](phase-3-smoke-triage.md).

It exercises page-scoped authority routing, hard rejection, publication safety,
CropBox/rotation preservation, and whole-document visual-authority escalation
without requiring private medical documents.

## File locations

| Artifact | Path |
|----------|------|
| Combined PDF | [`fixtures/synthetic/smoke/VeriDemand_Synthetic_PDF_Regression_Corpus_v1.0.pdf`](../../fixtures/synthetic/smoke/VeriDemand_Synthetic_PDF_Regression_Corpus_v1.0.pdf) |
| Manifest | [`fixtures/synthetic/smoke/VeriDemand_Synthetic_PDF_Regression_Manifest_v1.0.json`](../../fixtures/synthetic/smoke/VeriDemand_Synthetic_PDF_Regression_Manifest_v1.0.json) |
| Generator | [`scripts/generate_veridemand_regression_pdf.py`](../../scripts/generate_veridemand_regression_pdf.py) |
| Smoke runner | [`scripts/run_smoke_corpus.py`](../../scripts/run_smoke_corpus.py) |

## Checksums (SHA-256)

Recorded values are compared at smoke-runner startup:

- **PDF:** `373177016F10A6BA04142197F9A434AF8365493783F873C02B4E35889EC4FEA7`
- **Manifest:** `6E899DF6154317C5F2233E4FC90F5EBC2C55E18EA0BD30B37B892B1F5538D9EC`

If either file changes, update these values here **and** in
[`scripts/smoke_corpus/__init__.py`](../../scripts/smoke_corpus/__init__.py).

## Generation command

Regeneration needs ReportLab, Pillow, pypdf, and DejaVu/Noto fonts (typically
Linux CI or a font-equipped machine):

```bash
uv run python scripts/generate_veridemand_regression_pdf.py
```

Output defaults to `fixtures/synthetic/smoke/`. Override with
`VERIDEMAND_SMOKE_OUT`. After regenerating, recompute SHA-256 and update this
README plus `scripts/smoke_corpus/__init__.py`.

**Do not** regenerate casually on Windows if fonts differ — binary drift will
fail checksum validation.

## Validation commands

Backend must be running for API modes. Prefer a single dedicated API process
(avoid multiple `uvicorn --reload` instances fighting over the same port):

```bash
pnpm dev:backend
# or: uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

```bash
pnpm smoke:corpus:validate
pnpm smoke:corpus
pnpm smoke:corpus:page
pnpm smoke:corpus:whole
pnpm smoke:corpus:test-id -- T05
```

Override the API base URL when needed:

```bash
uv run python scripts/run_smoke_corpus.py --mode page-by-page --api-base-url http://127.0.0.1:8011 --critical-subset
```

Do not bind a long-lived smoke API on port **8010** — Playwright `chromium-holds` e2e uses that port.

Validate-only checks PDF/manifest presence, pypdf open, page counts, unique
test IDs, authority/viewer outcomes, privacy heuristics, and checksums.

## Page-by-page versus whole-document

**Page-by-page** splits each manifest page into a temporary single-page PDF
(preserving MediaBox, CropBox, and `/Rotate`), uploads it through the real
production API, and asserts against the manifest before the next test. Temporary
files are deleted unless `--keep-temporary-files` is set.

**Whole-document** uploads the combined PDF once, processes it through the real
coordinator, confirms the canonical PDF is viewable and page count matches, and
records document policy plus page decisions. Intentional bad pages may escalate
the whole document to visual authority; clean pages may become
`suppressed_by_document_escalation`. That is **not** scored as an individual-page
false failure.

## Current phase coverage (Phase 3 / 3.5)

`phase_expectation: current_phase_expected` — full authority, decision, Phase-3
reason-code, and publication-safety assertions. Includes clean native pages,
duplicate / near-overprint rejects, image-absent routing, geometry/visibility
rejects, unicode-noise rejects, CropBox/rotation/size cases, and mixed-content
baselines.

PR critical subset: **T01, T05, T10, T14, T20, T21, T41**.

## Future-phase coverage

`future_phase_expected` — hidden OCR and deep image-quality / handwriting cases
(T11–T13, T51–T54). Phase 3 **passes** when the page is safely routed to
`visual_authority` or `image_authority` with empty published text. It must **not**
fail merely because OCR is unimplemented.

`not_yet_implemented` — advisory features and reason codes outside the current
`NativeReasonCode` set (forms, annotations, OCG, ActualText, barcodes, etc.).
Runner enforces no-crash and publication safety only.

## Document-level limitations

The combined PDF is intentionally healthy at the document container level. These
are **out of scope** for page-scoped cases (see manifest
`document_scoped_exclusions`):

- password encryption
- digital signature validation
- malformed xref / trailer
- document-open JavaScript
- embedded file attachment
- linearisation or object-stream corruption

## How to add a new regression page

1. Add a `TestCase` + builder in `scripts/generate_veridemand_regression_pdf.py`.
2. Set `phase_expectation` appropriately (`current_phase_expected` only when
   Phase 3 can fully assert the outcome).
3. Use production `NativeReasonCode` strings for Phase-3 expected codes.
4. Regenerate the PDF/manifest on a font-equipped machine.
5. Update SHA-256 values in this README and `scripts/smoke_corpus/__init__.py`.
6. Extend the PR critical subset only for broadly representative failures.
7. Run `pnpm smoke:corpus:validate` and `pnpm smoke:corpus:test-id -- Txx`.

Never weaken production trust thresholds merely to make a synthetic page pass.
Classify failures as generator defect, manifest defect, genuine regression,
future-phase case, or unsupported document-scoped case.

# Private local regression fixtures (not committed)

This directory holds **local-only** documents used for regression and calibration against
real-world inputs. Everything here is git-ignored except this example README
(`fixtures/private/README.example.md`). **Never commit real documents, extracted text, or
derived hashes.**

Place files matching the categories below. Names are conventions only — no confidential
content is described or tracked here.

## Expected categories and example filenames

| Category | Example filename | What it exercises |
|----------|------------------|-------------------|
| Reliable native-text PDF | `native_text_clean.pdf` | Native extraction on a trustworthy text layer |
| Corrupt / misleading text-layer PDF | `native_text_corrupt.pdf` | Native-text trust gate rejection and visual fallback |
| Long scanned printed PDF | `scanned_printed_long.pdf` | Printed OCR path over many pages |
| Image-only scan (no text layer) | `image_only_scan.pdf` | Image/visual authority routing |
| Mixed printed + handwritten form | `mixed_print_handwritten_form.pdf` | Region detection and printed-vs-handwritten routing |
| Predominantly handwritten page | `handwritten_page.pdf` | Vision-LLM transcription routing (page authority) |
| Rotated / skewed scan | `rotated_or_skewed_scan.pdf` | Rotation/deskew handling |
| Table-heavy document | `tables_dense.pdf` | Table and cell structure detection |
| Single-page image input | `single_page_image.png` | Image-authority source mode |

## Native trust local manifest (Phase 3)

Create a **gitignored** file:

`fixtures/private/native-trust-manifest.local.json`

Example shape (opaque relative paths only; no patient names in keys):

```json
{
  "bad_native_primary": "opaque-relative-path.pdf",
  "bad_native_billing": "opaque-relative-path.pdf",
  "good_native_reference": "opaque-relative-path.pdf",
  "near_overprint_multi_cluster": {
    "file": "opaque-relative-path.pdf",
    "pages": [3, 5]
  }
}
```

Phase 3.5 worker regression `test_private_pages_3_and_5_worker_regression` uses
`near_overprint_multi_cluster` (skip if absent). It asserts each listed page is
either clean single-copy accept or `visual_authority` with empty text — never
geometrically interleaved doubles. No private text is printed.

Evaluate locally with:

`uv run python scripts/evaluate_private_native_trust.py`

The script prints only opaque labels, counts, policies, score stats, reason-code
counts, duration, and pass/fail — never text or filenames.

## Visual OCR local manifest (Phase 4)

Create a **gitignored** file:

`fixtures/private/visual-ocr-manifest.local.json`

Copy from `visual-ocr-manifest.local.json.example`. Use opaque relative paths only.

Evaluate locally with:

`uv run python scripts/evaluate_private_visual_ocr.py`

Output is opaque aggregates only (labels, page counts, confidence, duration,
pass/fail). Never commit private PDFs, transcripts, or the live `.local.json`
manifest.

Shareable synthetic OCR fixtures live under `fixtures/synthetic/ocr/`.
Never place private medical PDFs under `docs/example/`; that tree is for local notes only.

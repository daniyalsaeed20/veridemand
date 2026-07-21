# Licence inventory

## Summary

All Phase 0 and Phase 1 **direct** dependencies are under permissive licences
(MIT, MIT-CMU/HPND, BSD-2/3-Clause, Apache-2.0, or PSF-2.0). No copyleft
licence is present in the direct dependency set. Phase 1 introduces one
**transitive** GPL-3.0 package (`pcodedmp`, via `oletools`) that is flagged for
review below.

## Phase 1 direct dependency additions

| Package | Version | Licence | Notes |
|---|---|---|---|
| python-multipart | 0.0.32 | Apache-2.0 | Permissive; patent grant |
| sse-starlette | 3.4.6 | BSD-3-Clause | Permissive |
| pypdf | 5.9.0 | BSD-3-Clause | Permissive |
| Pillow | 11.3.0 | MIT-CMU (HPND) | Permissive (historical PIL/HPND licence) |
| oletools | 0.60.2 | BSD-2-Clause | Permissive |
| defusedxml | 0.7.1 | PSF-2.0 | Permissive |

## Direct dependency licence distribution

| Licence | Count (direct) | Notes |
|---|---|---|
| MIT | most Python + Node packages | Permissive |
| BSD-3-Clause | uvicorn, python-dotenv, httpx (+ transitive starlette, click) | Permissive |
| Apache-2.0 | pytest-asyncio, typescript, @playwright/test | Permissive; patent grant |

See `direct-dependencies.md` for the exact per-package versions and licences.

## Relevant transitive findings (Python, from `uv.lock` metadata)

- starlette - BSD-3-Clause
- anyio - MIT
- click - BSD-3-Clause
- pydantic-core - MIT
- h11, httpcore, certifi, idna, sniffio, typing-extensions, pyyaml,
  websockets, httptools, watchfiles, colorama - permissive (MIT / BSD / MPL-2.0
  for certifi's bundled data). No copyleft obligations affecting distribution of
  our source were identified.

Node transitive licences are predominantly MIT with some BSD/Apache/ISC, typical
of the React/Vite ecosystem. A full transitive audit tool (e.g. `license-checker`
or `pnpm licenses list`) can be run in a later phase if formal attestation is
required; no questionable dependency was added merely to produce a report.

## Copyleft / source-disclosure concerns

- **`pcodedmp` 1.2.6 - GPL-3.0 (transitive, via `oletools`).** This is a VBA
  p-code disassembler. VeriDemand only uses the `oletools` macro-**detection**
  API and never imports, invokes, distributes, or links `pcodedmp` p-code
  disassembly. As a runtime-only server component that is not distributed as a
  binary, no GPL distribution obligation is currently triggered. Flagged for
  manual review; if a stricter posture is required, pin/exclude `pcodedmp` or
  replace the macro-detection path with a direct `olefile` (BSD) stream check.

## Packages needing future review

- `pcodedmp` (GPL-3.0, transitive) - see the concern above.
- Later phases will add OCR (PaddleOCR), PDF (pdfplumber/pypdfium2),
  imaging (OpenCV), ONNX Runtime, the OpenAI SDK, and LibreOffice
  integration. Each must be licence-reviewed before it is added, per the
  dependency policy.

## Phase 1 confirmation

Confirmed: **no** OCR, MuPDF/PyMuPDF, HTR, vision-model, database, or
external-queue licences were introduced in Phase 1. `pypdf` and `Pillow` are
used strictly for upload validation. The only copyleft finding is the
transitive `pcodedmp` (GPL-3.0) noted above.

## Phase 0 confirmation

Confirmed: **no** OCR, MuPDF/PyMuPDF, HTR, or vision-model licences were
introduced in Phase 0. The heaviest runtime component is uvicorn's `standard`
extra (permissive) for local development.

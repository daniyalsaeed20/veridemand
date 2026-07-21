# Licence inventory

## Summary

All Phase 0 direct dependencies are under permissive licences (MIT, BSD-3-Clause,
or Apache-2.0). No copyleft (GPL/LGPL/AGPL) or source-disclosure licences were
introduced.

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

None identified for Phase 0.

## Packages needing future review

- None for Phase 0.
- Later phases will add OCR (PaddleOCR), PDF (pypdf/pdfplumber/pypdfium2),
  imaging (OpenCV/Pillow), ONNX Runtime, the OpenAI SDK, and LibreOffice
  integration. Each must be licence-reviewed before it is added, per the
  dependency policy.

## Phase 0 confirmation

Confirmed: **no** OCR, MuPDF/PyMuPDF, HTR, or vision-model licences were
introduced in Phase 0. The heaviest runtime component is uvicorn's `standard`
extra (permissive) for local development.

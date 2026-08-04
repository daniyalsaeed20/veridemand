# Licence inventory

## Summary

All Phase 0–2 **direct** Python and Node dependencies are under permissive
licences (MIT, MIT-CMU/HPND, BSD-2/3-Clause, Apache-2.0, or PSF-2.0). Phase 1
introduces one **transitive** GPL-3.0 package (`pcodedmp`, via `oletools`) that
is flagged for review below. Phase 2 adds **LibreOffice** as an external MPL-2.0
runtime (not a Python/Node package).

## Phase 4 direct dependency additions

| Package | Version | Licence | Notes |
|---|---|---|---|
| pypdfium2 | 5.12.1 | Apache-2.0 / BSD-3-Clause | Direct runtime dep for page rendering |
| numpy | 2.x | BSD-3-Clause | Visibility probes + OCR array ops |
| paddleocr | 3.7.0 | Apache-2.0 | Optional `ocr` group — printed OCR only |
| paddlepaddle | 3.3.0 | Apache-2.0 | Optional `ocr` group — CPU inference |
| psutil | 6.x–7.x | BSD-3-Clause | Optional `ocr` group — worker RSS monitoring |
| opencv-contrib-python (transitive) | via paddleocr | Apache-2.0 | Not imported by VeriDemand app code |

## Phase 5 direct dependency additions (Task 2 + Task B)

| Package | Version | Licence | Notes |
|---|---|---|---|
| onnxruntime | 1.28.0 | MIT | CPU inference for handwriting style classifier |
| onnx | 1.22.0 | Apache-2.0 | `model-dev` group only — checker / fixture generation |
| torch | 2.6.0 | BSD-3-Clause | `model-dev` only — classifier training/export; forbidden in production app |
| torchvision | 0.21.0 | BSD-3-Clause | `model-dev` only — MobileNetV3-Small + pretrained weights |
| onnxscript | resolved via lock | Apache-2.0 | `model-dev` only — PyTorch ONNX export helper |

Confirmed: no `openai`, `onnxruntime-gpu`, OpenCV app imports, or local HTR
engines were added in Task 2 / Task B. Torch/Torchvision remain outside the
production backend import boundary.

Confirmed: no handwriting/HTR classifiers, no ONNX Runtime vision packages, and
no OpenAI / vision-LLM client libraries were added in Phase 4.

## Phase 3 direct dependency additions

| Package | Version | Licence | Notes |
|---|---|---|---|
| pdfplumber | 0.11.9 | MIT | Native text/geometry only; no OCR/HTR/LLM |
| pdfminer.six (transitive) | 20251230 | MIT | Pulled by pdfplumber |
| pypdfium2 (transitive in Phase 3) | 5.12.1 | Apache-2.0 / BSD-3-Clause | Pulled by pdfplumber; promoted to direct use in Phase 4 |

Confirmed for Phase 3 exit: no OCR (Paddle/Tesseract), ONNX, OpenAI, or OpenCV
packages were added as direct dependencies at that time.

## Phase 2 direct dependency additions

| Package | Version | Licence | Notes |
|---|---|---|---|
| reportlab | 4.5.1 | BSD-3-Clause | Permissive; deterministic PDF generation |
| pdfjs-dist | 6.1.200 | Apache-2.0 | Permissive; patent grant. Ships optional WASM codecs (JBIG2/OpenJPEG/qcms) under `wasm/` with their own licence files; served at `/pdfjs-wasm/`. |

## Phase 2 external runtime

| Component | Licence | Notes |
|---|---|---|
| LibreOffice Writer | MPL-2.0 | External headless runtime; not vendored. Operators install locally or via CI (`libreoffice-writer`). File-based invocation only (`shell=False`). |

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
- Later phases will add OCR (PaddleOCR), additional PDF tooling, imaging (OpenCV),
  ONNX Runtime, and the OpenAI SDK. Each must be licence-reviewed before it is
  added, per the dependency policy.

## Phase 2 confirmation

Confirmed: **no** OCR, HTR, or vision-model Python/Node dependencies were
introduced in Phase 2. `reportlab` and `pdfjs-dist` are permissively licensed.
LibreOffice is an external MPL-2.0 runtime requirement, recorded separately.

## Phase 1 confirmation

Confirmed: **no** OCR, MuPDF/PyMuPDF, HTR, vision-model, database, or
external-queue licences were introduced in Phase 1. `pypdf` and `Pillow` are
used strictly for upload validation. The only copyleft finding is the
transitive `pcodedmp` (GPL-3.0) noted above.

## Phase 0 confirmation

Confirmed: **no** OCR, MuPDF/PyMuPDF, HTR, or vision-model licences were
introduced in Phase 0. The heaviest runtime component is uvicorn's `standard`
extra (permissive) for local development.

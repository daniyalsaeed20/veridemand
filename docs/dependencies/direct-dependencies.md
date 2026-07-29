# Direct dependencies

Exact versions are taken from the committed lockfiles (`uv.lock`,
`pnpm-lock.yaml`) and installed package metadata. Phases 0–4 are inventoried
below. Phase 4 adds printed OCR (optional `ocr` group), page rendering, hybrid
routing, and fair scheduling — still **no** handwriting/HTR classifiers,
vision-LLM clients, databases, or demand-letter packages.

## Python - runtime (`pyproject.toml` `[project].dependencies`)

| Package | Version | Purpose | Phase | Source | Licence |
|---|---|---|---|---|---|
| fastapi | 0.139.2 | Web framework / OpenAPI source | 0 | https://github.com/fastapi/fastapi | MIT |
| uvicorn[standard] | 0.51.0 | ASGI server (dev + prod) | 0 | https://github.com/encode/uvicorn | BSD-3-Clause |
| pydantic | 2.13.4 | Contract models / validation | 0 | https://github.com/pydantic/pydantic | MIT |
| pydantic-settings | 2.14.2 | Typed environment settings | 0 | https://github.com/pydantic/pydantic-settings | MIT |
| python-dotenv | 1.2.2 | `.env` loading in development | 0 | https://github.com/theskumar/python-dotenv | BSD-3-Clause |
| python-multipart | 0.0.32 | Receive multipart file uploads | 1 | https://github.com/Kludex/python-multipart | Apache-2.0 |
| sse-starlette | 3.4.6 | SSE responses, heartbeat, disconnect handling | 1 | https://github.com/sysid/sse-starlette | BSD-3-Clause |
| pypdf | 5.9.0 | PDF structural validation, encryption check, page count; Phase 3 structural inspection | 1–3 | https://github.com/py-pdf/pypdf | BSD-3-Clause |
| Pillow | 11.3.0 | Image identification, integrity, dimensions, frame count only | 1 | https://github.com/python-pillow/Pillow | MIT-CMU (HPND) |
| oletools | 0.60.2 | Detect VBA macros in legacy `.doc` files | 1 | https://github.com/decalage2/oletools | BSD-2-Clause |
| defusedxml | 0.7.1 | Safely inspect XML metadata in DOCX packages | 1 | https://github.com/tiran/defusedxml | PSF-2.0 |
| reportlab | 4.5.1 | Deterministic TXT/image → canonical PDF | 2 | https://www.reportlab.com/devdocs/ | BSD-3-Clause |
| pdfplumber | 0.11.9 | Native character/word extraction and geometry (no rendering) | 3 | https://github.com/jsvine/pdfplumber | MIT |
| pypdfium2 | 5.12.1 | Canonical page rendering for visibility probes and printed OCR | 4 | https://github.com/pypdfium2-team/pypdfium2 | Apache-2.0 / BSD-3-Clause |
| numpy | 2.x | Visibility-probe image math (no OpenCV in app code) | 4 | https://numpy.org/ | BSD-3-Clause |

### Phase 4 OCR optional group (`[dependency-groups].ocr`)

Installed via `uv sync --group ocr` / `pnpm models:ocr:bootstrap`. Not required for
canonicalisation or native trust. No handwriting classifiers or vision-LLM
packages are included.

| Package | Version | Purpose | Phase | Source | Licence |
|---|---|---|---|---|---|
| paddleocr | 3.7.0 | Printed text detection + recognition (PP-OCRv6) | 4 | https://github.com/PaddlePaddle/PaddleOCR | Apache-2.0 |
| paddlepaddle | 3.3.0 | CPU inference runtime for PaddleOCR | 4 | https://github.com/PaddlePaddle/Paddle | Apache-2.0 |
| pypdfium2 | 5.12.1 | Same pin as runtime; used by OCR worker rendering | 4 | https://github.com/pypdfium2-team/pypdfium2 | Apache-2.0 / BSD-3-Clause |
| numpy | ≥2,<3 | Array ops for OCR / visibility | 4 | https://numpy.org/ | BSD-3-Clause |
| psutil | ≥6,<8 | OCR worker RSS monitoring / recycle heuristics | 4 | https://github.com/giampaolo/psutil | BSD-3-Clause |

**Transitive note:** `paddleocr` may pull `opencv-contrib-python` (Apache-2.0).
VeriDemand application code does **not** import OpenCV; visibility probes use
Pillow + NumPy only. No ONNX handwriting classifier and no OpenAI/vision-LLM
packages are Phase 4 dependencies.

### Phase 3 transitive notes

`pdfplumber` 0.11.9 depends on `pdfminer.six` **20251230** (MIT) for text
extraction and also depends on `pypdfium2` **5.12.1**. Phase 4 now **directly**
depends on and imports `pypdfium2` for rendering under
`backend/app/extraction/visual/`. A dependency-boundary guard still forbids OCR
imports outside the visual package.

## External runtime (not a Python package)

| Component | Version | Purpose | Phase | Source | Licence |
|---|---|---|---|---|---|
| LibreOffice Writer | host-specific | Headless DOC/DOCX → PDF canonicalisation | 2 | https://www.libreoffice.org/ | MPL-2.0 |

Discovered via `LIBREOFFICE_EXECUTABLE`, `PATH`, or known install paths. Required
for readiness and Word canonicalisation; not vendored in the repository.

## Python - development (`[dependency-groups].dev`)

| Package | Version | Purpose | Phase | Source | Licence |
|---|---|---|---|---|---|
| httpx | 0.28.1 | Test client transport | 0 | https://github.com/encode/httpx | BSD-3-Clause |
| pytest | 8.4.2 | Test runner | 0 | https://github.com/pytest-dev/pytest | MIT |
| pytest-asyncio | 1.4.0 | Async test support | 0 | https://github.com/pytest-dev/pytest-asyncio | Apache-2.0 |
| ruff | 0.15.22 | Lint + format | 0 | https://github.com/astral-sh/ruff | MIT |
| mypy | 1.20.2 | Static type checking | 0 | https://github.com/python/mypy | MIT |

Python direct-dependency licences were confirmed from the installed dist-info
METADATA in the uv-managed environment.

### Phase 1 notable transitive dependencies (from `oletools`)

`oletools` pulls in `olefile` (BSD), `msoffcrypto-tool` (MIT), `cryptography`
(Apache-2.0 OR BSD-3-Clause), `pyparsing`/`colorclass`/`easygui`/`cffi`/
`pycparser`/`win-unicode-console` (permissive), and **`pcodedmp` 1.2.6
(GPL-3.0)**. `pcodedmp` is a VBA p-code disassembler. VeriDemand only calls the
`oletools` macro-**detection** API (`VBA_Parser.detect_vba_macros`) and never
disassembles or distributes p-code. The GPL-3.0 transitive dependency is
recorded here and flagged for manual review in `licence-inventory.md`; it is not
imported directly by application code.

## Node - frontend runtime (`frontend/package.json` `dependencies`)

| Package | Version | Purpose | Phase | Source | Licence |
|---|---|---|---|---|---|
| react | 19.2.7 | UI library | 0 | https://github.com/facebook/react | MIT |
| react-dom | 19.2.7 | React DOM renderer | 0 | https://github.com/facebook/react | MIT |
| @mui/material | 9.2.0 | Component library / theme | 0 | https://github.com/mui/material-ui | MIT |
| @mui/icons-material | 9.2.0 | Icon set | 0 | https://github.com/mui/material-ui | MIT |
| @emotion/react | 11.14.0 | MUI styling engine | 0 | https://github.com/emotion-js/emotion | MIT |
| @emotion/styled | 11.14.1 | MUI styling engine | 0 | https://github.com/emotion-js/emotion | MIT |
| @tanstack/react-query | 5.101.3 | Server-state / health queries | 0 | https://github.com/TanStack/query | MIT |
| zustand | 5.0.14 | Ephemeral shell state | 0 | https://github.com/pmndrs/zustand | MIT |
| zod | 4.4.3 | Runtime response validation | 0 | https://github.com/colinhacks/zod | MIT |
| pdfjs-dist | 6.1.200 | In-browser canonical PDF viewer (PDF.js) | 2 | https://github.com/mozilla/pdf.js | Apache-2.0 |

## Node - frontend development (`frontend/package.json` `devDependencies`)

| Package | Version | Purpose | Phase | Source | Licence |
|---|---|---|---|---|---|
| typescript | 5.9.3 | Type system / build | 0 | https://github.com/microsoft/TypeScript | Apache-2.0 |
| vite | 8.1.5 | Dev server / bundler | 0 | https://github.com/vitejs/vite | MIT |
| @vitejs/plugin-react | 6.0.3 | React plugin for Vite | 0 | https://github.com/vitejs/vite-plugin-react | MIT |
| vitest | 4.1.10 | Unit test runner | 0 | https://github.com/vitest-dev/vitest | MIT |
| jsdom | 29.1.1 | DOM environment for tests | 0 | https://github.com/jsdom/jsdom | MIT |
| @testing-library/react | 16.3.2 | Component testing | 0 | https://github.com/testing-library/react-testing-library | MIT |
| @testing-library/jest-dom | 6.9.1 | DOM matchers | 0 | https://github.com/testing-library/jest-dom | MIT |
| @testing-library/user-event | 14.6.1 | User interaction testing | 0 | https://github.com/testing-library/user-event | MIT |
| eslint | 10.7.0 | Linter | 0 | https://github.com/eslint/eslint | MIT |
| typescript-eslint | 8.64.0 | TypeScript ESLint tooling | 0 | https://github.com/typescript-eslint/typescript-eslint | MIT |
| eslint-plugin-react-hooks | 7.1.1 | React hooks lint rules | 0 | https://github.com/facebook/react | MIT |
| eslint-plugin-react-refresh | 0.5.3 | React Fast Refresh lint | 0 | https://github.com/ArnaudBarre/eslint-plugin-react-refresh | MIT |
| @eslint/js | 10.0.1 | ESLint JS recommended config | 0 | https://github.com/eslint/eslint | MIT |
| globals | 17.7.0 | Global variable definitions | 0 | https://github.com/sindresorhus/globals | MIT |
| prettier | 3.9.5 | Formatter | 0 | https://github.com/prettier/prettier | MIT |
| @hey-api/openapi-ts | 0.99.0 (exact) | TS + Zod contract generation | 0 | https://github.com/hey-api/openapi-ts | MIT |
| @playwright/test | 1.61.1 | E2E smoke test | 0 | https://github.com/microsoft/playwright | Apache-2.0 |
| @types/react | 19.2.17 | React type definitions | 0 | https://github.com/DefinitelyTyped/DefinitelyTyped | MIT |
| @types/react-dom | 19.2.3 | React DOM type definitions | 0 | https://github.com/DefinitelyTyped/DefinitelyTyped | MIT |

## Node - root (`package.json` `devDependencies`)

| Package | Version | Purpose | Phase | Source | Licence |
|---|---|---|---|---|---|
| concurrently | 9.2.0 | Run dev servers together | 0 | https://github.com/open-cli-tools/concurrently | MIT |

Node licences are the well-known SPDX identifiers published by each project. If
any value later proves inaccurate it should be corrected here and marked
`UNKNOWN - manual licence review required` until confirmed.

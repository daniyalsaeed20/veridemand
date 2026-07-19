# Dependency Inventory (Phase 3)

**Date:** 2026-07-20  
**Supported Python:** `>=3.12,<3.13` (lock built with 3.12.x)  
**Supported Node:** `>=22 <25` (`.nvmrc` → 22)

Licences verified from package metadata at install time. Re-verify on upgrades.

---

## Backend — runtime

| Package | Version | Purpose | Licence | Scope |
|---------|---------|---------|---------|-------|
| fastapi | 0.116.1 | HTTP API framework | MIT | runtime |
| uvicorn[standard] | 0.35.0 | ASGI server | BSD-3-Clause | runtime |
| pydantic | 2.11.7 | Authoritative machine contracts | MIT | runtime |
| pydantic-settings | 2.10.1 | Settings helpers | MIT | runtime |
| python-multipart | 0.0.20 | Multipart form parsing for file uploads | Apache-2.0 | runtime |
| pypdf | 5.9.0 | PDF signature/encryption checks and safe page counts | BSD-3-Clause | runtime |
| Pillow | 11.3.0 | Image open/verify, OCR preprocess, TIFF frames | HPND | runtime |
| pdfplumber | 0.11.7 | Native PDF text extraction (Phase 2+) | MIT | runtime |
| pypdfium2 | 4.30.0 | Page render / thumbnails / OCR input (sole boundary) | Apache-2.0 / BSD-3-Clause | runtime |
| paddleocr | 2.7.3 | Printed English OCR (Phase 3; OD-16 pin A) | Apache-2.0 | runtime |
| paddlepaddle | 2.6.2 | Paddle runtime for PaddleOCR (CPU) | Apache-2.0 | runtime |
| opencv-python-headless | 4.9.0.80 | Lightweight OCR preprocess (deskew/threshold) | Apache-2.0 | runtime |
| numpy | ≥1.23,<2 | Array bridge for OCR/OpenCV (Paddle 2.6 requires `<2`) | BSD-3-Clause | runtime |
| psutil | 7.x (locked) | Optional resource probes / acceptance metrics | BSD-3-Clause | runtime |
| starlette | 0.47.3 | (transitive via FastAPI) ASGI toolkit | BSD-3-Clause | runtime |

Lockfile: [`backend/uv.lock`](backend/uv.lock)

### OCR model cache (not a pip package)

- Models are **not** committed to Git.
- Default cache: `%LOCALAPPDATA%/VeriDemand/paddleocr` (Windows) or `~/.cache/veridemand/paddleocr`.
- Override with `VERIDEMAND_OCR_MODEL_DIR`.
- On first OCR, PaddleOCR downloads English det/rec/cls weights into that directory.
- `/health` reports `capabilities.ocr_enabled=true` when paddle packages import; models may still lazy-load on first use.

---

## Backend — development / test

| Package | Version | Purpose | Licence | Scope |
|---------|---------|---------|---------|-------|
| pytest | 8.4.1 | Unit/integration/golden tests | MIT | development |
| pytest-asyncio | 1.1.0 | Async test support | Apache-2.0 | development |
| httpx | 0.28.1 | TestClient transport | BSD-3-Clause | development |
| ruff | 0.12.4 | Lint + format | MIT | development |
| mypy | 1.17.0 | Static type checking | MIT | development |

---

## Frontend — runtime

| Package | Version | Purpose | Licence | Scope |
|---------|---------|---------|---------|-------|
| react | 19.1.0 | UI | MIT | runtime |
| react-dom | 19.1.0 | DOM renderer | MIT | runtime |
| zod | 3.25.76 | API response validation | MIT | runtime |
| zustand | 5.0.6 | Shell state scaffold | MIT | runtime |
| pdfjs-dist | (locked) | Canonical PDF viewer | Apache-2.0 | runtime |

## Frontend — development

| Package | Version | Purpose | Licence | Scope |
|---------|---------|---------|---------|-------|
| vite | 7.0.5 | Dev server + production bundler | MIT | development |
| typescript | 5.8.3 | Strict typing | Apache-2.0 | development |
| @vitejs/plugin-react | 4.7.0 | React transform | MIT | development |
| vitest | 3.2.4 | Unit tests | MIT | development |
| eslint + typescript-eslint | 9.31.0 / 8.38.0 | Lint | MIT | development |
| prettier | 3.6.2 | Format | MIT | development |
| json-schema-to-zod | 2.6.1 | Generate Zod from JSON Schema | MIT | development |

Lockfile: [`frontend/package-lock.json`](frontend/package-lock.json)

---

## Explicitly excluded

| Package | Note |
|---------|------|
| PaddleOCR 3.x | Failed on measured Windows/oneDNN host — do not install |
| Paid DocAI | Not default extractor |
| Database drivers | No database in prototype |
| LLM SDKs for extraction | No LLM-first extraction |

---

## Contract generation chain

```text
docs/contracts/*.md → Pydantic (backend/app/models)
                   → JSON Schema (contracts/generated/)
                   → Zod (frontend/src/schemas/generated/) via json-schema-to-zod
```

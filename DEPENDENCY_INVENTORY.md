# Dependency Inventory (Phase 1)

**Date:** 2026-07-19  
**Supported Python:** `>=3.12,<3.13` (lock built with 3.12.8)  
**Supported Node:** `>=22 <25` (`.nvmrc` → 22; CI/dev measured on Node 24.18.0 locally)

Licences verified from package metadata at install time. Re-verify on upgrades.

---

## Backend — runtime

| Package | Version | Purpose | Licence | Scope |
|---------|---------|---------|---------|-------|
| fastapi | 0.116.1 | HTTP API framework | MIT | runtime |
| uvicorn[standard] | 0.35.0 | ASGI server | BSD-3-Clause | runtime |
| pydantic | 2.11.7 | Authoritative machine contracts | MIT | runtime |
| pydantic-settings | 2.10.1 | Settings helpers (available; AppSettings uses custom env load) | MIT | runtime |
| python-multipart | 0.0.20 | Multipart form parsing for file uploads | Apache-2.0 | runtime |
| pypdf | 5.9.0 | PDF signature/encryption checks and safe page counts (no text extraction) | BSD-3-Clause | runtime |
| Pillow | 11.3.0 | Image open/verify and TIFF frame counts | HPND | runtime |
| starlette | 0.47.3 | (transitive via FastAPI) ASGI toolkit | BSD-3-Clause | runtime |
| anyio / httpx / … | locked in `backend/uv.lock` | Transitive runtime support | various | runtime |

## Backend — development / test

| Package | Version | Purpose | Licence | Scope |
|---------|---------|---------|---------|-------|
| pytest | 8.4.1 | Unit/integration/golden tests | MIT | development |
| pytest-asyncio | 1.1.0 | Async test support | Apache-2.0 | development |
| httpx | 0.28.1 | TestClient transport | BSD-3-Clause | development |
| ruff | 0.12.4 | Lint + format | MIT | development |
| mypy | 1.17.0 | Static type checking | MIT | development |

Lockfile: [`backend/uv.lock`](backend/uv.lock)

---

## Frontend — runtime

| Package | Version | Purpose | Licence | Scope |
|---------|---------|---------|---------|-------|
| react | 19.1.0 | UI | MIT | runtime |
| react-dom | 19.1.0 | DOM renderer | MIT | runtime |
| zod | 3.25.76 | API response validation | MIT | runtime |
| zustand | 5.0.6 | Shell state scaffold | MIT | runtime |

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

## Explicitly excluded from the Phase 0 application

| Package | Note |
|---------|------|
| PaddleOCR | **Not installed** in app. Phase 3 constraint from readiness OCR spike: pin **PaddleOCR 2.7.3** + **PaddlePaddle 2.6.2**. Do not migrate to 3.x during Phase 0. Remains under `spikes/ocr/` only. |
| PaddlePaddle | Same as above |
| pdfplumber / pypdfium2 / OpenCV | Later phases; spike-only today |
| Database drivers | No database in prototype |

---

## Contract generation chain

```text
docs/contracts/*.md → Pydantic (backend/app/models)
                   → JSON Schema (contracts/generated/)
                   → Zod (frontend/src/schemas/generated/) via json-schema-to-zod
```

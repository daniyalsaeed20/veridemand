# Dependency Inventory (foundation shell)

**Date:** 2026-07-21
**Supported Python:** `>=3.12,<3.13` (lock built with 3.12.x)
**Supported Node:** `>=22 <25` (`.nvmrc` → 22)

Licences verified from package metadata. Re-verify on upgrades. Extraction-specific
dependencies (PDF/OCR/vision) are intentionally **not** present in this foundation shell and
will be added, with justification, when the corresponding specification phase is implemented.

---

## Backend — runtime

| Package | Version | Purpose | Licence | Scope |
|---------|---------|---------|---------|-------|
| fastapi | 0.116.1 | HTTP API framework | MIT | runtime |
| uvicorn[standard] | 0.35.0 | ASGI server | BSD-3-Clause | runtime |
| pydantic | 2.11.7 | Authoritative machine contracts | MIT | runtime |
| starlette | (transitive via FastAPI) | ASGI toolkit | BSD-3-Clause | runtime |

Lockfile: [`backend/uv.lock`](backend/uv.lock)

## Backend — development / test

| Package | Version | Purpose | Licence | Scope |
|---------|---------|---------|---------|-------|
| pytest | 8.4.1 | Unit/integration tests | MIT | development |
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

## Explicitly excluded (for now)

| Package / category | Note |
|--------------------|------|
| PDF/OCR/vision libraries (pdfplumber, pypdf, pypdfium2, PaddleOCR, OpenCV, Pillow, numpy) | Removed in the reset; reintroduce per specification phases with justification |
| Database drivers | No database in the foundation shell |
| LLM SDKs | No LLM calls in the foundation shell |

---

## Contract generation chain

```text
backend/app/models (Pydantic) → contracts/generated/*.schema.json
                              → frontend/src/schemas/generated/*.ts (json-schema-to-zod)
```

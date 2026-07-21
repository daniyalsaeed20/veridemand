# VeriDemand

Document-extraction platform. This repository is currently a minimal, runnable
**foundation shell**: a FastAPI backend exposing health endpoints and a React frontend that
reports backend health. No extraction features are implemented yet.

- Canonical specification: [`docs/VeriDemand_Document_Extraction_Source_of_Truth_v1.0.md`](docs/VeriDemand_Document_Extraction_Source_of_Truth_v1.0.md)
- Reset decision record: [`docs/decisions/0001-reset-to-document-extraction.md`](docs/decisions/0001-reset-to-document-extraction.md)
- Dependencies: [`DEPENDENCY_INVENTORY.md`](DEPENDENCY_INVENTORY.md)
- Cleanup audit / report: [`docs/cleanup/`](docs/cleanup/)

## Endpoints

- `GET /api/v1/health/live` — liveness.
- `GET /api/v1/health/ready` — readiness.

## Quick start

```powershell
# Backend (from repo root)
.\.tools\python312\python.exe -m uv sync --extra dev --project backend
backend\.venv\Scripts\uvicorn.exe app.main:app --app-dir backend --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm ci
npm run dev
```

One-command quality gate: `node scripts/check-all.mjs`

## Contract generation chain

```text
backend/app/models (Pydantic) → contracts/generated/*.schema.json
                              → frontend/src/schemas/generated/*.ts (json-schema-to-zod)
```

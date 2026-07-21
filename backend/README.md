# VeriDemand Backend

Minimal FastAPI foundation for the document-extraction platform. Exposes the health
endpoints only; no extraction features are implemented yet.

- `GET /api/v1/health/live` — liveness.
- `GET /api/v1/health/ready` — readiness.

Canonical specification: [`../docs/VeriDemand_Document_Extraction_Source_of_Truth_v1.0.md`](../docs/VeriDemand_Document_Extraction_Source_of_Truth_v1.0.md).

## Local development

```powershell
# Create/refresh the virtualenv and install (from repo root)
.\.tools\python312\python.exe -m uv pip install -e "backend[dev]" --python backend\.venv\Scripts\python.exe

# Run the API
backend\.venv\Scripts\uvicorn.exe app.main:app --app-dir backend --reload --port 8000
```

## Checks

```powershell
backend\.venv\Scripts\python.exe -m ruff check app tests
backend\.venv\Scripts\python.exe -m mypy app
backend\.venv\Scripts\python.exe -m pytest -q
```

# Local setup (Phase 1)

## Prerequisites

- Python **3.12** (repo ships a local interpreter under `.tools/python312/` when present)
- Node.js **22+** (see `.nvmrc`)
- Git

## Backend

```powershell
# From repo root
.\.tools\python312\Scripts\uv.exe sync --directory backend --extra dev

# Run API
backend\.venv\Scripts\uvicorn.exe app.main:app --app-dir backend --reload --port 8000
```

Optional env (server bootstrap; not part of contracted `AppSettings` entity fields):

```text
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
LOG_LEVEL=INFO
APP_VERSION=0.0.0-dev
TEMP_ROOT=   # default: <repo>/tmp/sessions
MAX_ACTIVE_SESSIONS=32
SESSION_CLEANUP_INTERVAL_SECONDS=60
```

Appendix D / `AppSettings` overrides use names like `SESSION_TTL_MINUTES`, `MAX_FILES_PER_SESSION`, `MAX_FILE_SIZE_MB`, `MAX_TOTAL_UPLOAD_MB`, `MAX_PAGES_PER_SESSION`, etc.

Health check:

```powershell
curl http://127.0.0.1:8000/api/v1/health
```

Create a temporary session:

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/sessions
```

## Frontend

```powershell
cd frontend
npm ci
copy .env.example .env   # sets VITE_API_BASE_URL
npm run dev
```

Open http://localhost:5173 — Temporary Prototype banner, start session, upload supported files, reset case.

## Contracts

```powershell
backend\.venv\Scripts\python.exe scripts\generate_json_schemas.py
node scripts\generate-zod.mjs
node scripts\check-contracts.mjs
```

## One-command quality gate

```powershell
node scripts\check-all.mjs
```

Runs backend format/lint/types/tests, contract generate+drift proof, and frontend format/lint/types/tests/build.

## Temporary / ignored paths

Session and temp runtime dirs (`tmp/`, `data/sessions/`), `docs/example` PDFs/DOCX, spike `out/`, `.tools/`, venvs, and `node_modules/` are gitignored. Do not commit case binaries.

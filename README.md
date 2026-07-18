# VeriDemand

Demand-letter automation prototype.

- Canonical doctrine: [`docs/prototype_documentation.md`](docs/prototype_documentation.md)
- Contracts: [`docs/contracts/`](docs/contracts/)
- Modules: [`docs/modules/README.md`](docs/modules/README.md)
- Local setup (Phase 0): [`docs/local-setup.md`](docs/local-setup.md)
- Dependencies: [`DEPENDENCY_INVENTORY.md`](DEPENDENCY_INVENTORY.md)
- Phase 0 report: [`docs/implementation-reports/phase-00-completion.md`](docs/implementation-reports/phase-00-completion.md)

## Quick start

```powershell
# Backend
.\.tools\python312\python.exe -m uv pip install -e "backend[dev]" --python backend\.venv\Scripts\python.exe
backend\.venv\Scripts\uvicorn.exe app.main:app --app-dir backend --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm ci
npm run dev
```

One-command quality gate: `node scripts/check-all.mjs`

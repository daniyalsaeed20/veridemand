# ADR 0001 - Monorepo tooling

- Status: Accepted
- Date: 2026-07-21
- Phase: 0

## Context

VeriDemand is a single product with a Python (FastAPI) backend and a
TypeScript (React/Vite) frontend. We need reproducible environments, a single
place to orchestrate quality gates, and first-class Windows support.

## Decision

- **pnpm (via Corepack)** manages the frontend workspace. The repository root is
  a private, non-publishable pnpm workspace (`pnpm-workspace.yaml` lists only
  `frontend`). The exact pnpm version is pinned in the root `package.json`
  `packageManager` field.
- **uv** manages the Python environment and lockfile at the repository root
  (`pyproject.toml` + `uv.lock`). The backend is installed as an editable
  package so `backend.app.*` imports resolve everywhere.
- **Root orchestration**: all developer commands run from the repository root
  through `pnpm` scripts. Cross-platform orchestration that would otherwise need
  shell-specific syntax is implemented in Python (`scripts/check_all.py`,
  `scripts/check_contracts.py`) rather than Bash. `concurrently` runs the two
  dev servers together.

## Runtime baseline (as installed)

- **Python**: uv-managed **3.12** (`.python-version` pins `3.12`;
  `requires-python = ">=3.12,<3.13"`). The developer machine's system Python
  3.13 remains installed and untouched; the global `python` command is not
  altered. All Python commands run through `uv run` / `uv sync`.
- **Node.js**: **24.18.0** (already installed). `.nvmrc` pins `24.18.0`; the root
  `engines.node` is `">=24.18.0 <25"`.
- **pnpm**: `11.15.1` via Corepack.

This is a recorded deviation from the original Phase 0 prompt, which specified
Python 3.12 (kept) and Node 22 (changed to 24.18.0). The change was approved to
use the least-invasive side-by-side runtime setup on the target machine.

## Consequences

- Reproducible installs via `uv.lock` and `pnpm-lock.yaml`, enforced with
  frozen installs in CI.
- Windows, macOS and Linux all use the same root commands.
- Contributors must use `uv run` for backend commands; invoking the global
  `python` is not supported for project tasks.

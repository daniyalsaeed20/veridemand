# Direct dependencies

Exact versions are taken from the committed lockfiles (`uv.lock`,
`pnpm-lock.yaml`) and installed package metadata. Phase 0 introduces **no**
OCR, PDF, image, MuPDF, HTR, vision-model, database, or queue dependencies.

## Python - runtime (`pyproject.toml` `[project].dependencies`)

| Package | Version | Purpose | Phase | Source | Licence |
|---|---|---|---|---|---|
| fastapi | 0.139.2 | Web framework / OpenAPI source | 0 | https://github.com/fastapi/fastapi | MIT |
| uvicorn[standard] | 0.51.0 | ASGI server (dev + prod) | 0 | https://github.com/encode/uvicorn | BSD-3-Clause |
| pydantic | 2.13.4 | Contract models / validation | 0 | https://github.com/pydantic/pydantic | MIT |
| pydantic-settings | 2.14.2 | Typed environment settings | 0 | https://github.com/pydantic/pydantic-settings | MIT |
| python-dotenv | 1.2.2 | `.env` loading in development | 0 | https://github.com/theskumar/python-dotenv | BSD-3-Clause |

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

# Phase 0 - Foundation architecture

This document describes the foundation shell delivered in Phase 0. No upload,
session, queue, rendering, OCR, detection, routing, LLM, or extraction feature
is implemented.

## Monorepo layout

```text
veridemand/
├── backend/            # FastAPI app (installed as an editable package)
│   ├── app/
│   │   ├── main.py             # create_app() application factory
│   │   ├── api/                # routers (health at root; empty /api/v1)
│   │   ├── contracts/          # Pydantic API models (source of truth)
│   │   ├── settings/           # pydantic-settings configuration
│   │   ├── observability/      # request-id middleware + error handlers
│   │   ├── health/             # readiness/liveness evaluation
│   │   └── <future-phase dirs> # README-only extension points
│   └── tests/
├── frontend/           # Vite + React + TypeScript (pnpm workspace)
│   └── src/
│       ├── app/                # providers, theme, query client, store, shell
│       ├── api/                # environment + fetch helper
│       ├── contracts/          # generated types + Zod (barrel in index.ts)
│       ├── components/         # header, runtime warning, phase status
│       └── features/health/    # health API, hook, status card
├── docs/contracts/openapi.json # committed, generated OpenAPI
└── scripts/            # contract generation + validation orchestration
```

## Backend application factory

`create_app(settings: Settings | None = None) -> FastAPI` builds the app with no
heavy work at import time: no future models are loaded and no global processing
service is constructed. It sets API metadata (title `VeriDemand API`, version
`0.1.0`, description "Runtime-only document extraction platform API."), stores
settings and a `HealthService` on `app.state`, registers the request-id
middleware, CORS (from `FRONTEND_ORIGIN`), exception handlers, and the routers.
`app = create_app()` is exported for `uvicorn`.

## Router boundaries

- Health routes are mounted at the application root, matching the canonical
  contract: `GET /health/live`, `GET /health/ready`.
- The versioned router (`/api/v1`) is intentionally empty; later phases add
  their routes there.

## Settings flow

Environment variables (overriding a development `.env`) are parsed and validated
by a frozen `Settings` model. `OPENAI_API_KEY` is a `SecretStr` and never
appears in `repr`, logs, or responses. Thresholds are constrained to `[0, 1]`;
counts and byte limits must be positive; `API_PREFIX` must start with `/`;
`FRONTEND_ORIGIN` must be a valid URL. A cached `get_settings()` serves the
process; tests inject a `Settings` into `create_app` without touching global
state.

## Request-ID and error-envelope flow

```text
request ─▶ RequestIdMiddleware ─▶ route handler ─▶ response (+ X-Request-ID)
              │  validate/generate id            ▲
              └────────── request.state.request_id ┘
                                   │
        exception ─▶ exception handler ─▶ ApiErrorEnvelope (+ X-Request-ID)
```

An inbound `X-Request-ID` is preserved only when safe and bounded
(`^[A-Za-z0-9._-]{1,128}$`); otherwise a UUID hex id is generated. Every
response echoes `X-Request-ID`. Exception handlers (`RequestValidationError`,
Starlette `HTTPException`, and unhandled `Exception`) return the canonical
`ApiErrorEnvelope` with the request id, log server-side with that id, and never
expose stack traces or filesystem paths.

## Contract generation flow

```text
Pydantic models ─▶ FastAPI OpenAPI ─▶ scripts/generate_contracts.py
   ─▶ docs/contracts/openapi.json ─▶ @hey-api/openapi-ts
   ─▶ frontend/src/contracts/generated/{types.gen.ts, zod.gen.ts, index.ts}
```

`scripts/check_contracts.py` proves determinism (generate twice, compare
hashes) and fails on any `git diff` in the committed contracts.

## Frontend provider hierarchy

```text
QueryClientProvider ─▶ ThemeProvider ─▶ CssBaseline ─▶ App
```

The TanStack Query cache is never persisted (runtime-only principle). Zustand
holds only ephemeral shell state and is never persisted.

## Frontend health-query flow

`useLiveness` / `useReadiness` (TanStack Query) call `healthApi`, which uses the
small `getJson` fetch helper (timeout via `AbortController`) and validates each
response with the generated Zod schema before returning generated TypeScript
types. `HealthStatusCard` renders process/readiness state, backend URL, last
successful check, and request id, with a manual retry control.

## Why future dependencies are not loaded in Phase 0

Extraction, OCR, rendering, and vision libraries (pypdf, pdfplumber, pypdfium2,
PaddleOCR, OpenCV, Pillow, ONNX Runtime, OpenAI, LibreOffice) are **not**
installed. Their configuration contracts exist in `Settings`, and their
readiness checks are optional `not_configured` placeholders, but no code imports
or activates them. This keeps the foundation small, fast, and honest about what
is actually implemented.

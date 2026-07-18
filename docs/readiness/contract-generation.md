# Contract Generation Recommendation

**Status date:** 2026-07-19  
**Goal:** Keep Pydantic, JSON Schema, and frontend TypeScript/Zod synchronized without hand-maintained duplicate field shapes.

---

## Recommendation (committed)

| Layer | Role |
|-------|------|
| [`docs/contracts/`](../contracts/) Markdown | **Human design SoT** for entity fields, enums, taxonomies, error codes |
| **Pydantic v2 models** (Phase 0 `backend/app/models/`) | **Authoritative machine schema** at runtime |
| **JSON Schema export** from Pydantic (`model_json_schema()` / FastAPI OpenAPI components) | Checked artifact for FE generation and CI |
| **Generated Zod** (or TS types + Zod) in `frontend/src/schemas/` | Frontend validation; **not** hand-edited field shapes |
| **CI drift check** | Fail if regenerated Zod/OpenAPI differs from committed generated output |

```text
docs/contracts/*.md  --(implement)-->  Pydantic models
                                          |
                                          v
                                   JSON Schema / OpenAPI
                                          |
                          +---------------+---------------+
                          |                               |
                          v                               v
                   generate Zod                     contract tests
                   (frontend)                       (backend)
```

**Do not** maintain a second parallel field table in TypeScript.  
**Do not** redefine fields in module docs (already forbidden).

This supersedes the temporary “hand-maintained Zod mirrors until CI generation” bootstrap note in [`docs/contracts/README.md`](../contracts/README.md) as the **target** Phase 0 end state. A one-time bootstrap copy is acceptable only until the generator runs the first time.

---

## Tooling chain (preferred)

1. **Export:** Pydantic v2 → JSON Schema (draft 2020-12 or OpenAPI 3.1 components via FastAPI).  
2. **Generate FE:** `json-schema-to-zod` (or equivalent maintained generator) from the exported schemas for entities used on the wire (`HealthResponse` first).  
3. **Validate:** pytest compares backend `model_validate` round-trips to FE fixture JSON; optional `npm run schemas:check` regenerates and `git diff --exit-code`.

### Still requires confirmation (non-blocking for starting Phase 0)

| Decision | Candidates | Note |
|----------|------------|------|
| Zod generator package | `json-schema-to-zod`, `openapi-typescript` + zod helpers, `orval` | Pick one in Phase 0 PR; record purpose, version, licence |
| Commit generated files vs generate-only in CI | Commit generated Zod for reviewability | **Recommend commit** generated schemas so reviews see FE impact |
| Single OpenAPI file vs per-entity JSON Schema files | Per-entity under `contracts/generated/` or `backend/schemas/` | Prefer per-entity matching `docs/contracts/entities/` names |

Confirmation of the generator package does **not** block Phase 0 kickoff if the Phase 0 PR itself selects and inventories one chain.

---

## Phase 0 minimum

1. Implement `HealthResponse` + `AppSettings` (+ enums) in Pydantic from Markdown contracts.  
2. Export JSON Schema for `HealthResponse`.  
3. Generate Zod for `HealthResponse`.  
4. Integration test: FastAPI `/api/v1/health` body validates in both Pydantic and Zod.  
5. Document dependency purpose/version/licence (Cursor production-dependency rule).

---

## Explicitly rejected

| Approach | Why |
|----------|-----|
| Long-term hand-maintained Zod duplicates | Drift; violates readiness preference |
| TypeScript as machine SoT | Backend is source of validated API payloads |
| Markdown-only without Pydantic | No runtime validation |
| Generating Pydantic from Zod | Inverts selected stack (§6.2) |

---

## Relation to taxonomies

`fact-types.md` / `issue-types.md` / `error-codes.md` should become:

- Python `Literal` / `Enum` or frozen sets used by validators, **and**
- Generated TS string-union / zod enums from the same export,

so parsers and UI cannot invent undeclared codes without a contracts changelog.

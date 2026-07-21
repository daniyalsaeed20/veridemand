# 0001 — Reset to a document-extraction foundation

- Status: Accepted
- Date: 2026-07-21

## Context

The repository previously implemented a demand-letter automation prototype (sessions,
uploads, OCR, deterministic legal fact extraction, issues, drafting, verification, and
export). A new canonical specification,
`docs/VeriDemand_Document_Extraction_Source_of_Truth_v1.0.md`, redefines VeriDemand as a
general **document-extraction platform**. The old implementation, docs, contracts, and rules
conflicted with the new specification and could not be incrementally reconciled without
carrying excluded scope forward.

## Decision

Perform a controlled, destructive reset on a dedicated cleanup branch, archiving the original
HEAD first:

- Delete the obsolete demand-letter implementation, documentation, contracts, spikes,
  templates, and Cursor rules.
- Keep only: the canonical specification; domain-neutral infrastructure (logging, request-id
  middleware, error envelope, server settings); the codegen/drift tooling; and the synthetic
  extraction fixtures (rebuilt to extraction-only ground truth).
- Rebuild a minimal, runnable FastAPI + React **health shell** with
  `GET /api/v1/health/live` and `GET /api/v1/health/ready`.
- Trim contracts to `HealthResponse` and `ErrorEnvelope`; regenerate JSON Schema and Zod.
- Ignore `fixtures/private/*` (except `README.example.md`) so local regression documents are
  never committed.

## Scope boundaries confirmed

- The demand-letter product scope is removed and out of scope going forward.
- No dedicated local HTR in V1; handwritten and uncertain regions route directly to the
  configured vision LLM. Local detection and page geometry remain authoritative.
- No features are implemented in this reset. No upload, queue, session, rendering, OCR,
  detection, routing, LLM, SSE, document viewer, or extraction behaviour is added.
- No CI or Docker configuration existed before the reset; none was added.

## Consequences

- History for the old product remains available on
  `archive/pre-document-extraction-reset-20260721`.
- Future work starts from a clean, verified foundation aligned with the canonical
  specification and its phase roadmap.
- The rebuilt synthetic fixtures are future gold inputs only; no active test consumes them
  until the corresponding extraction phase is implemented.

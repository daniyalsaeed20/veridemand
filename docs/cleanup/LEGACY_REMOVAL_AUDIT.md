# Legacy Removal Audit — Reset to Document-Extraction Foundation

Date: 2026-07-21
Cleanup branch: `cleanup/reset-document-extraction`
Archive branch: `archive/pre-document-extraction-reset-20260721` @ `31178d9`
Original HEAD recorded: `31178d964005efed3650c9f3372f1af5985736bd`

Canonical specification (sole source of truth): `docs/VeriDemand_Document_Extraction_Source_of_Truth_v1.0.md`.

This audit classifies every significant area of the repository at the original HEAD as
`PRESERVE`, `REBUILD_MINIMALLY`, `REMOVE`, or `REVIEW`. The reset deletes the obsolete
demand-letter product and rebuilds only a minimal, runnable FastAPI + React health shell.
No extraction features are implemented.

## Classification legend

- PRESERVE — domain-neutral infrastructure reusable as-is under the new specification.
- REBUILD_MINIMALLY — concept/file is useful but was coupled to the old product; rewritten to the minimal shell.
- REMOVE — old demand-letter/legal-workflow scope explicitly excluded by the specification.
- REVIEW — inspected and confirmed safe (rewritten or kept) after review.

## Backend (`backend/`)

### PRESERVE
- `app/__init__.py`
- `app/core/logging.py`
- `app/core/middleware.py` (request-id)
- `app/core/server_settings.py` (rebuilt to shell scope; see REBUILD)
- `app/services/__init__.py` (empty)
- `tests/unit/test_repo_hygiene.py` (extended with fixtures/private assertions)
- `tests/unit/test_logging.py`

### REBUILD_MINIMALLY
- `app/main.py` — app factory reduced to logging + RequestId + CORS + error handlers + health router; all old services and `AppSettings` coupling removed.
- `app/api/__init__.py`, `app/api/v1/__init__.py` — health-only router.
- `app/api/v1/health.py` — split into `GET /api/v1/health/live` and `GET /api/v1/health/ready`.
- `app/services/health.py` — liveness/readiness only; OCR/LLM capability probing removed.
- `app/models/health.py` — `HealthResponse` trimmed; `HealthCapabilities` removed.
- `app/models/taxonomies.py` — `FACT_TYPES`/`ISSUE_TYPES` removed; `ErrorCode` trimmed to generic codes (`route_not_found`, `validation_error`, `internal_error`, `not_implemented`); `CONTRACTS_VERSION` kept.
- `app/models/enums.py` — trimmed to `HealthStatus` only.
- `app/models/error_envelope.py` — trimmed to `error_code`, `message`, `details`, `request_id`.
- `app/models/registry.py` — `ContractRegistry` reduced to `HealthResponse` + `ErrorEnvelope`.
- `app/models/__init__.py` — exports reduced to the surviving contracts.
- `app/core/errors.py` — exception handlers rewritten without `DomainError`.
- `app/core/server_settings.py` — trimmed to CORS/log/app-version (session/OCR/LibreOffice/thumbnail fields removed).
- `tests/integration/test_health.py` — rewritten for `/health/live` + `/health/ready`.
- `tests/unit/test_contracts.py` — rewritten to assert only `HealthResponse` + `ErrorEnvelope`.
- `pyproject.toml` — dependencies trimmed to `fastapi`, `uvicorn[standard]`, `pydantic` (dev: `httpx`, `mypy`, `pytest`, `pytest-asyncio`, `ruff`); `uv.lock` regenerated.
- `README.md`, `.env.example` — rewritten for the shell.

### REMOVE (old product)
- `app/api/v1/sessions.py`
- `app/core/domain_errors.py`
- `app/models/`: `app_settings.py`, `billing_entry.py`, `case_session.py`, `document.py`, `document_page.py`, `document_upload_batch.py`, `draft_section.py`, `export_result.py`, `fact.py`, `geometry.py`, `issue.py`, `money.py`, `preflight.py`, `process_event.py`, `source_span.py`, `source_token.py`, `timeline_event.py`, `user_decision.py`
- `app/services/`: `billing/`, `classification/`, `documents/`, `drafting/`, `export/`, `extraction/`, `facts/`, `issues/`, `llm/`, `ocr/`, `process/`, `session/`, `timeline/`, `verification/`, `harness.py`
- `scripts/phase03_reference_acceptance.py`
- `tests/fixtures/` (`__init__.py`, `upload_builders.py`), `tests/helpers_process.py`, `tests/golden/`
- All old `tests/integration/*` except `test_health.py`
- All old `tests/unit/*` except `test_repo_hygiene.py`, `test_logging.py`, `test_contracts.py`
  (removed: `test_classification_*`, `test_coordinates`, `test_docx_security`, `test_extraction_*`,
  `test_fact_*`, `test_log_hygiene_phase02`, `test_native_*`, `test_ocr_*`, `test_pdfium_*`,
  `test_phase05_gold_validator`, `test_session`, `test_settings`, `test_span_grouping`,
  `test_upload_*`)

## Frontend (`frontend/`)

### PRESERVE
- `index.html`, `vite.config.ts`, `tsconfig.json`, `eslint.config.js`, `.prettierrc.json`, `.prettierignore`
- `src/main.tsx`, `src/vite-env.d.ts`

### REBUILD_MINIMALLY
- `src/app/App.tsx` — brand + "Document extraction foundation reset." + backend health state only.
- `src/api/client.ts` — transport + `fetchHealth()` (`/api/v1/health/live`) only.
- `src/schemas/health.ts`, `src/schemas/health.test.ts` — capabilities removed.
- `src/fixtures/health-ok.json` — capabilities removed.
- `src/styles.css` — trimmed to shell classes.
- `package.json` — `pdfjs-dist` and `zustand` removed; `package-lock.json` refreshed.
- `.env.example` — reviewed (kept `VITE_API_BASE_URL`).

### REMOVE (old product)
- `src/components/` (`DocumentList.tsx`, `DocumentViewer.tsx`, `FactsPanel.tsx`, `documentClassification.ts`, `factsPanel.test.ts`)
- `src/store/shellStore.ts`
- `src/schemas/documents.ts`, `src/schemas/session.ts`, `src/schemas/session.test.ts`, `src/schemas/viewer.ts`, `src/schemas/viewer.test.ts`
- All `src/schemas/generated/*` except regenerated `HealthResponse` + `ErrorEnvelope` (see Contracts)

## Contracts + codegen

### PRESERVE / REBUILD
- `scripts/generate_json_schemas.py`, `scripts/generate-zod.mjs`, `scripts/check-contracts.mjs`, `scripts/check-all.mjs`, `scripts/proof-drift-fails.mjs` — kept (domain-neutral tooling); `check-all.mjs` trimmed to the shell gate.
- `contracts/generated/*` — regenerated from the trimmed registry to `HealthResponse` + `ErrorEnvelope` + `index.json`.
- `fixtures/health-ok.json` — capabilities removed.

### REMOVE
- All `contracts/generated/*` for deleted entities (regenerated set contains only Health + ErrorEnvelope).
- `scripts/generate_phase05_gold_review.py`, `scripts/validate_phase05_gold_review.py`, `scripts/phase05_gold_review_schema.json`, `scripts/requirements-gold.txt`
- `scripts/extraction_acceptance/` (remediation review app, scorers, schema) — see fixtures for the retained builder.

## Synthetic extraction fixtures (`fixtures/extraction_acceptance/`)

17 fixture concepts existed at the original HEAD. Every `ground_truth.json` mixed valid new
extraction concepts (pages, lines, words, polygons, reading order, source mode, rotation) with
old-harness/legal metadata (`annotation_status`, `expected_outcome` review states,
`native_trustworthy`, `corrupt_embedded`, `must_reject_corrupt`, `silent_mix`, and legal
`critical_fields` such as `person_name`, `law_firm_name`, `badge_id`). Therefore none qualified
as PRESERVE as-is.

### REMOVE (2) — excluded scope (critical-fact / legal-field extraction + verification)
- `person_name_field`
- `law_firm_name_field`

### REBUILD_MINIMALLY (15) — synthetic media kept; ground truth rewritten to new concepts only
- `clean_native_paragraph`, `two_column_page`, `table_page`, `label_value_form`,
  `header_footer_page`, `rotated_text_page`, `skewed_scan_page`, `image_only_no_text_layer`,
  `image_with_correct_hidden_ocr`, `corrupt_hidden_ocr`, `boxed_individual_characters`,
  `mixed_print_handwritten_like`, `diagram_grid_labels`, `overlapping_duplicate_hidden_text`,
  `date_identifier_fields`

Rebuilt fixtures are documented **future gold inputs with no active test** (the consuming tests
are removed). Expected outputs use only: documents, pages, regions, blocks, lines, words, tables,
cells, coordinates (normalized, top-left origin, `[0,1]`), source modes, script types,
recognition methods, and warnings. No `critical_fields`, review states, or legal metadata remain.
`scripts/extraction_acceptance/build_synthetic_fixtures.py` is rebuilt and relocated to a
domain-neutral path; `MANIFEST.json` and `README.md` are updated.

### Fixture counts
- Preserved: 0
- Rebuilt: 15
- Removed: 2

## Docs (`docs/`)

### PRESERVE
- `docs/VeriDemand_Document_Extraction_Source_of_Truth_v1.0.md` (canonical spec; committed on the cleanup branch)

### ADD (cleanup + decision records)
- `docs/cleanup/LEGACY_REMOVAL_AUDIT.md` (this file)
- `docs/cleanup/RESET_REPORT.md`
- `docs/decisions/0001-reset-to-document-extraction.md`

### REMOVE (old product doctrine, modules, readiness, reports, examples, remediation)
- `docs/prototype_documentation.md`, `docs/prototype_documentation.docx`
- `docs/local-setup.md`
- `docs/contracts/`
- `docs/modules/`
- `docs/readiness/`
- `docs/implementation-reports/`
- `docs/example/`
- `docs/remediation/`

## Spikes / templates

### REMOVE
- `spikes/billing/`, `spikes/docx-template/`, `spikes/ocr/`, `spikes/phase05_fact_acceptance_probe.py`
- `templates/` (`.gitkeep`, `README.md`)

## Cursor rules (`.cursor/rules/`)

### REMOVE
- `veridemand-doctrine.mdc` (demand-letter phase doctrine)
- `veridemand-evidence.mdc` (demand-letter evidence/gold doctrine)

### ADD
- `veridemand-source-of-truth.mdc` (points at the canonical spec; encodes excluded scope, phase boundaries, HTR policy, stop-and-report)

## Root files

### PRESERVE
- `.gitignore` (extended with `fixtures/private/*` + `!fixtures/private/README.example.md`)
- `.gitattributes`, `.nvmrc`

### REBUILD_MINIMALLY
- `README.md`, `DEPENDENCY_INVENTORY.md`

## CI / Docker

No CI configuration and no Docker configuration existed at the original HEAD (no `.github/`,
no `Dockerfile`, no compose file). None is added by this reset. CI is deferred to a later,
explicitly reviewed foundation task.

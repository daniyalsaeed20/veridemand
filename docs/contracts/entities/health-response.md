# Entity: HealthResponse

| Field | Value |
|-------|-------|
| Spec | §14.1 / Phase 0 |
| Owning module(s) | [00 Repository and Contracts](../../modules/00-repository-and-contracts.md) |
| contracts_version | 0.1 |

## 1. Purpose

Safe health payload for `GET /api/v1/health`. No secrets, paths, session data, or document text.

## 2. Fields

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `status` | HealthStatus | yes | enum | |
| `api_version` | string | yes | e.g. `v1` | |
| `app_version` | string | no | semver or git describe | |
| `contracts_version` | string | yes | e.g. `0.1` | Matches this pack |
| `time_utc` | datetime | yes | ISO-8601 | |
| `capabilities` | object | yes | non-sensitive flags | See example |
| `message` | string | no | | Degraded reason |

### capabilities (suggested keys)

| Name | Type | Notes |
|------|------|-------|
| `ocr_enabled` | bool | |
| `llm_semantic_extraction_enabled` | bool | Default false |
| `max_files_per_session` | int | |
| `max_pages_per_session` | int | |

## 3. Validation rules

- Never include API keys, temp roots, or filenames of case documents.

## 4. Example JSON

```json
{
  "status": "ok",
  "api_version": "v1",
  "app_version": "0.0.0-dev",
  "contracts_version": "0.1",
  "time_utc": "2026-07-18T12:00:00Z",
  "capabilities": {
    "ocr_enabled": true,
    "llm_semantic_extraction_enabled": false,
    "max_files_per_session": 20,
    "max_pages_per_session": 300
  },
  "message": null
}
```

## 5. Open / additive notes

Release/version source (package metadata vs git) is an implementation choice; field remains optional.

# Entity: AppSettings

| Field | Value |
|-------|-------|
| Spec | Appendix D / Phase 0 |
| Owning module(s) | [00 Repository and Contracts](../../modules/00-repository-and-contracts.md) |
| contracts_version | 0.1 |

## 1. Purpose

Validated runtime configuration for the prototype. Loaded from environment; never returned with secrets in API responses.

## 2. Fields

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `session_ttl_minutes` | int | yes | `> 0` | Default `120` |
| `max_files_per_session` | int | yes | `> 0` | Default `20` |
| `max_pages_per_session` | int | yes | `> 0` | Default `300` |
| `max_file_size_mb` | int | yes | `> 0` | Default `75` |
| `max_total_upload_mb` | int | yes | `> 0` | Default `250` |
| `ocr_workers` | int | yes | `== 1` for prototype | Default `1` |
| `ocr_render_dpi` | int | yes | typically `150–300` | Default `200` |
| `ocr_retry_dpi` | int | yes | `>= ocr_render_dpi` | Default `300` |
| `native_min_chars` | int | yes | `> 0` | Default `40` — see [03-ocr-thresholds](../../modules/03-ocr-thresholds.md) |
| `native_min_text_coverage` | float | yes | `0–1` | Default `0.02` |
| `native_max_replacement_ratio` | float | yes | `0–1` | Default `0.05` |
| `native_max_zero_width_or_overlap_ratio` | float | yes | `0–1` | Default `0.15` |
| `native_min_reading_order_score` | float | yes | `0–1` | Default `0.55` |
| `native_likely_scan_image_coverage` | float | yes | `0–1` | Default `0.60` |
| `native_long_token_band` | int | yes | `> 0` | Default `40` — tokens longer than this count toward long-token ratio |
| `native_max_long_token_ratio` | float | yes | `0–1` | Default `0.20` |
| `native_max_mean_token_length` | float | yes | `> 0` | Default `24` |
| `native_max_median_token_length` | float | yes | `> 0` | Default `18` |
| `native_min_printable_ratio` | float | yes | `0–1` | Default `0.90` |
| `native_max_control_char_ratio` | float | yes | `0–1` | Default `0.02` |
| `native_max_oversized_box_ratio` | float | yes | `0–1` | Default `0.20` |
| `ocr_page_mean_conf_low` | float | yes | `0–1` | Default `0.55` |
| `ocr_page_mean_conf_retry_trigger` | float | yes | `0–1` | Default `0.70` |
| `enable_llm_semantic_extraction` | bool | yes | | Default `false` |
| `llm_extraction_temperature` | float | yes | `>= 0` | Default `0` |
| `llm_draft_temperature` | float | yes | `>= 0` | Default `0.2` |
| `allow_vision_crop_fallback` | bool | yes | | Default `true` |
| `allow_final_export_with_red_issues` | bool | yes | | Default `false` |
| `log_document_text` | bool | yes | | Default `false` |

## 3. Validation rules

- Out-of-range env values fail startup with a safe message (no secret leakage).
- `get_safe_config_summary()` may expose non-sensitive subset only.

## 4. Example JSON

```json
{
  "session_ttl_minutes": 120,
  "max_files_per_session": 20,
  "max_pages_per_session": 300,
  "max_file_size_mb": 75,
  "max_total_upload_mb": 250,
  "ocr_workers": 1,
  "ocr_render_dpi": 200,
  "ocr_retry_dpi": 300,
  "native_min_chars": 40,
  "native_min_text_coverage": 0.02,
  "native_max_replacement_ratio": 0.05,
  "native_max_zero_width_or_overlap_ratio": 0.15,
  "native_min_reading_order_score": 0.55,
  "native_likely_scan_image_coverage": 0.60,
  "native_long_token_band": 40,
  "native_max_long_token_ratio": 0.20,
  "native_max_mean_token_length": 24,
  "native_max_median_token_length": 18,
  "native_min_printable_ratio": 0.90,
  "native_max_control_char_ratio": 0.02,
  "native_max_oversized_box_ratio": 0.20,
  "ocr_page_mean_conf_low": 0.55,
  "ocr_page_mean_conf_retry_trigger": 0.70,
  "enable_llm_semantic_extraction": false,
  "llm_extraction_temperature": 0,
  "llm_draft_temperature": 0.2,
  "allow_vision_crop_fallback": true,
  "allow_final_export_with_red_issues": false,
  "log_document_text": false
}
```

## 5. Open / additive notes

Env var names match Appendix D (`SESSION_TTL_MINUTES`, etc.) plus native/OCR knobs from [03-ocr-thresholds.md](../../modules/03-ocr-thresholds.md) (`NATIVE_MIN_CHARS`, …). Additional feature flags may be added in a later contracts version.

**Changelog:** 2026-07-18 — added provisional native usability and OCR page-confidence settings (Pass 3).  
**Changelog:** 2026-07-20 — added pathological tokenization knobs (Phase 2 hardening B-02; still `0.1-provisional`).

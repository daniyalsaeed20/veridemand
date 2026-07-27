// Canonical document / overlay-proof API for the Phase 2 viewer.
//
// TEMPORARY CONTRACT OVERRIDES
// -----------------------------------------------------------------------------
// `frontend/src/contracts/generated/*` is mechanically generated from the
// committed OpenAPI document and is currently stale relative to the Phase 2
// backend contracts (`backend/app/contracts/documents.py`,
// `backend/app/contracts/canonical.py`, `backend/app/contracts/geometry.py`,
// `backend/app/contracts/progress.py`): it still models the Phase 1
// `DocumentStatus` (with `preparing` instead of `canonicalising`) and does not
// know about the canonical-view fields on `DocumentSummary`, the new
// canonicalisation progress event types, or the canonical/overlay-proof
// response shapes at all.
//
// Per project doctrine, hand-maintained duplicate field shapes are not a
// long-term substitute for generated contracts. These types/schemas are an
// explicitly *temporary* bridge, scoped to this file, so the viewer (and the
// small number of call sites that must stay in sync with it) can compile
// against and safely parse the real backend shape. Delete this block and
// switch call sites back to `../../contracts` once `generate:contracts` is
// re-run against the Phase 2 OpenAPI document.
// -----------------------------------------------------------------------------

import { z } from "zod";

import { environment } from "../../api/environment";
import { getJson } from "../../api/http";
import {
  zDocumentFormat,
  zJobSummary,
  zPageCountStatus,
  zQueueInfo,
  zRejectedDocument,
  zSessionLimits,
} from "../../contracts";

// Duplicated from `../session/sessionApi` (rather than imported) to avoid a
// circular dependency: `sessionApi.ts` imports the temporary session/document
// schemas from this module.
function sessionPath(sessionId: string): string {
  return `/api/v1/sessions/${sessionId}`;
}

// ---------------------------------------------------------------------------
// Canonical status / method enums (backend/app/contracts/canonical.py)
// ---------------------------------------------------------------------------

export const zCanonicalStatus = z.enum([
  "pending",
  "queued",
  "canonicalising",
  "ready",
  "failed",
  "cancelled",
]);
export type CanonicalStatus = z.infer<typeof zCanonicalStatus>;

export const zCanonicalisationMethod = z.enum([
  "original_pdf",
  "libreoffice_writer_pdf",
  "reportlab_text_pdf",
  "reportlab_image_pdf",
]);
export type CanonicalisationMethod = z.infer<typeof zCanonicalisationMethod>;

export const zCanonicalPageSourceType = z.enum(["pdf", "text", "image", "word"]);
export type CanonicalPageSourceType = z.infer<typeof zCanonicalPageSourceType>;

// ---------------------------------------------------------------------------
// Normalised geometry (backend/app/contracts/geometry.py)
// ---------------------------------------------------------------------------

export const zNormalizedPoint = z.object({
  x: z.number().gte(0).lte(1),
  y: z.number().gte(0).lte(1),
});
export type NormalizedPointDto = z.infer<typeof zNormalizedPoint>;

export const zNormalizedBoundingBox = z.object({
  x: z.number().gte(0).lte(1),
  y: z.number().gte(0).lte(1),
  width: z.number().gt(0).lte(1),
  height: z.number().gt(0).lte(1),
});
export type NormalizedBoundingBoxDto = z.infer<typeof zNormalizedBoundingBox>;

export const zNormalizedPolygon = z.object({
  points: z.array(zNormalizedPoint).min(3).max(64),
});

export const zGeometry = z.object({
  polygon: zNormalizedPolygon,
  bbox: zNormalizedBoundingBox,
});
export type GeometryDto = z.infer<typeof zGeometry>;

// ---------------------------------------------------------------------------
// Canonical document / page metadata
// ---------------------------------------------------------------------------

export const zCanonicalPageMetadata = z.object({
  page_number: z.int().gte(1),
  width_points: z.number().gt(0),
  height_points: z.number().gt(0),
  intrinsic_rotation: z.union([z.literal(0), z.literal(90), z.literal(180), z.literal(270)]),
  source_type: zCanonicalPageSourceType,
  source_frame_index: z.int().gte(0).nullish(),
  source_pixel_width: z.int().gt(0).nullish(),
  source_pixel_height: z.int().gt(0).nullish(),
  image_placement_bbox: zNormalizedBoundingBox.nullish(),
});
export type CanonicalPageMetadata = z.infer<typeof zCanonicalPageMetadata>;

export const zCanonicalDocumentMetadata = z.object({
  document_id: z.string(),
  canonical_status: zCanonicalStatus,
  canonicalisation_method: zCanonicalisationMethod,
  media_type: z.string(),
  size_bytes: z.int().gte(0),
  sha256: z.string().length(64),
  page_count: z.int().gte(1),
  pages: z.array(zCanonicalPageMetadata),
  created_at: z.iso.datetime(),
  libreoffice_version: z.string().nullish(),
  warnings: z.array(z.string()).default([]),
});
export type CanonicalDocumentMetadata = z.infer<typeof zCanonicalDocumentMetadata>;

// ---------------------------------------------------------------------------
// Synthetic overlay proof (Phase 2 alignment verification only — never real
// extraction output; `synthetic` is always true).
// ---------------------------------------------------------------------------

export const zOverlayProofItem = z.object({
  id: z.string(),
  label: z.string(),
  source: z.string(),
  synthetic: z.boolean(),
  page_number: z.int().gte(1),
  geometry: zGeometry,
});
export type OverlayProofItem = z.infer<typeof zOverlayProofItem>;

export const zOverlayProofResponse = z.object({
  document_id: z.string(),
  synthetic: z.boolean().default(true),
  overlays: z.array(zOverlayProofItem),
});
export type OverlayProofResponse = z.infer<typeof zOverlayProofResponse>;

// ---------------------------------------------------------------------------
// DocumentStatus / DocumentSummary — extended with `canonicalising` and the
// canonical-view fields (backend/app/contracts/documents.py).
// ---------------------------------------------------------------------------

export const MAX_PHASE3_PROGRESS_PERCENT = 35;
export const MAX_PHASE4_PROGRESS_PERCENT = 65;

export const zDocumentStatus = z.enum([
  "uploaded",
  "queued",
  "canonicalising",
  "ready_for_extraction",
  "inspecting_native",
  "extracting_native",
  "native_trust_complete",
  "visual_pending",
  "visual_processing",
  "visual_processing_complete",
  "visual_processing_partial",
  "visual_processing_failed",
  "cancelled",
  "failed",
]);
export type DocumentStatus = z.infer<typeof zDocumentStatus>;

export const zDocumentSummary = z.object({
  document_id: z.string(),
  display_filename: z.string(),
  extension: z.string(),
  format: zDocumentFormat,
  media_type: z.string(),
  size_bytes: z.int().gte(0),
  sha256: z.string().length(64),
  page_count: z.int().gte(0).nullish(),
  page_count_status: zPageCountStatus,
  status: zDocumentStatus,
  progress_percent: z.int().gte(0).lte(MAX_PHASE4_PROGRESS_PERCENT),
  result_available: z.boolean().default(false),
  extraction_performed: z.boolean().default(false),
  native_extraction_performed: z.boolean().default(false),
  native_result_available: z.boolean().default(false),
  visual_processing_required: z.boolean().default(false),
  visual_processing_performed: z.boolean().default(false),
  visual_result_available: z.boolean().default(false),
  document_source_policy: z
    .enum([
      "native_authority",
      "embedded_ocr_authority",
      "mixed_authority",
      "visual_authority",
      "image_authority",
    ])
    .nullish(),
  user_status_message: z.string().nullish(),
  failure_stage: z.string().nullish(),
  failure_code: z.string().nullish(),
  failure_message: z.string().nullish(),
  failure_page_number: z.int().gte(1).nullish(),
  warning_count: z.int().gte(0).default(0),
  queue_position: z.int().gte(1).nullish(),
  active_job_id: z.string().nullish(),
  created_at: z.iso.datetime(),
  canonical_status: zCanonicalStatus.nullish(),
  canonicalisation_method: zCanonicalisationMethod.nullish(),
  canonical_view_available: z.boolean().default(false),
  canonical_view_url: z.string().nullish(),
  canonical_metadata_url: z.string().nullish(),
  native_summary_url: z.string().nullish(),
  visual_summary_url: z.string().nullish(),
  pages_completed: z.int().gte(0).nullish(),
  pages_total: z.int().gte(0).nullish(),
  major_phase: z.string().nullish(),
  major_phase_percent: z.number().gte(0).lte(100).nullish(),
  page_percent: z.number().gte(0).lte(100).nullish(),
  active_page_number: z.int().gte(1).nullish(),
  current_operation: z.string().nullish(),
  operation_status: z.string().nullish(),
  progress_kind: z.string().nullish(),
  elapsed_seconds: z.number().gte(0).nullish(),
  document_elapsed_seconds: z.number().gte(0).nullish(),
  page_elapsed_seconds: z.number().gte(0).nullish(),
  operation_elapsed_seconds: z.number().gte(0).nullish(),
  deadline_remaining_seconds: z.number().gte(0).nullish(),
  worker_generation: z.int().gte(0).nullish(),
  worker_restart_count: z.int().gte(0).nullish(),
  attempt_number: z.int().gte(1).nullish(),
  max_attempts: z.int().gte(1).nullish(),
  stage_timeline: z.array(z.record(z.string(), z.unknown())).nullish(),
  progress_version: z.int().gte(1).nullish(),
  current_route: z.string().nullish(),
  estimate_status: z.string().nullish(),
  estimate_confidence: z.string().nullish(),
  estimate_sample_count: z.int().gte(0).nullish(),
  estimated_document_remaining_seconds: z.number().gte(0).nullish(),
  estimated_queue_remaining_seconds: z.number().gte(0).nullish(),
  estimated_completion_at: z.iso.datetime().nullish(),
  estimated_current_operation_seconds: z.number().gte(0).nullish(),
  estimated_current_page_seconds: z.number().gte(0).nullish(),
  average_page_seconds: z.number().gte(0).nullish(),
  average_full_ocr_page_seconds: z.number().gte(0).nullish(),
  pages_per_minute: z.number().gte(0).nullish(),
  document_pages_total: z.int().gte(0).nullish(),
  native_pages_retained: z.int().gte(0).nullish(),
  embedded_ocr_pages_verified: z.int().gte(0).nullish(),
  targeted_repair_pages_selected: z.int().gte(0).nullish(),
  targeted_repair_pages_completed: z.int().gte(0).nullish(),
  full_ocr_pages_selected: z.int().gte(0).nullish(),
  full_ocr_pages_completed: z.int().gte(0).nullish(),
  full_ocr_pages_remaining: z.int().gte(0).nullish(),
  pages_remaining: z.int().gte(0).nullish(),
  fair_scheduling_enabled: z.boolean().nullish(),
  document_started_at: z.iso.datetime().nullish(),
  phase_started_at: z.iso.datetime().nullish(),
  page_started_at: z.iso.datetime().nullish(),
  operation_started_at: z.iso.datetime().nullish(),
  phase_elapsed_seconds: z.number().gte(0).nullish(),
  server_timestamp: z.iso.datetime().nullish(),
});
export type DocumentSummary = z.infer<typeof zDocumentSummary>;

export const zDocumentStatusCounts = z.object({
  uploaded: z.int().gte(0).default(0),
  queued: z.int().gte(0).default(0),
  canonicalising: z.int().gte(0).default(0),
  ready_for_extraction: z.int().gte(0).default(0),
  inspecting_native: z.int().gte(0).default(0),
  extracting_native: z.int().gte(0).default(0),
  native_trust_complete: z.int().gte(0).default(0),
  visual_pending: z.int().gte(0).default(0),
  visual_processing: z.int().gte(0).default(0),
  visual_processing_complete: z.int().gte(0).default(0),
  visual_processing_partial: z.int().gte(0).default(0),
  visual_processing_failed: z.int().gte(0).default(0),
  cancelled: z.int().gte(0).default(0),
  failed: z.int().gte(0).default(0),
});
export type DocumentStatusCounts = z.infer<typeof zDocumentStatusCounts>;

// ---------------------------------------------------------------------------
// ProgressEventType / ProgressEvent — extended with the canonicalisation and
// page-level event types plus the canonical_* fields
// (backend/app/contracts/progress.py).
// ---------------------------------------------------------------------------

export const zProgressEventType = z.enum([
  "session.created",
  "session.snapshot",
  "session.expiring",
  "session.deleted",
  "document.uploaded",
  "document.rejected",
  "document.queued",
  "document.started",
  "document.stage_changed",
  "document.canonicalisation_started",
  "document.canonicalisation_progress",
  "document.canonicalisation_completed",
  "document.canonicalisation_failed",
  "document.canonicalisation_cancelled",
  "document.canonical_ready",
  "document.ready_for_extraction",
  "document.native_inspection_started",
  "document.native_page_started",
  "document.native_page_accepted",
  "document.native_page_rejected",
  "document.native_page_absent",
  "document.native_page_error",
  "document.native_document_escalated",
  "document.native_extraction_completed",
  "document.native_extraction_failed",
  "document.visual_processing_started",
  "document.visual_pages_selected",
  "document.native_visibility_started",
  "document.native_visibility_supported",
  "document.native_visibility_rejected",
  "document.visual_page_started",
  "document.visual_page_rendered",
  "document.visual_page_ocr_started",
  "document.visual_page_ocr_completed",
  "document.visual_page_no_text",
  "document.visual_page_failed",
  "document.visual_grouping_completed",
  "document.visual_processing_completed",
  "document.visual_processing_partial",
  "document.visual_processing_failed",
  "document.page_route_started",
  "document.page_route_completed",
  "document.embedded_ocr_visual_check_started",
  "document.embedded_ocr_visual_check_completed",
  "document.embedded_ocr_recognition_check_started",
  "document.embedded_ocr_recognition_check_completed",
  "document.embedded_ocr_verified",
  "document.embedded_ocr_targeted_repair_started",
  "document.embedded_ocr_targeted_repair_completed",
  "document.full_ocr_primary_started",
  "document.full_ocr_primary_completed",
  "document.full_ocr_fallback_started",
  "document.full_ocr_fallback_completed",
  "document.visual_no_text_completed",
  "document.removed",
  "document.warning",
  "document.failed",
  "document.cancelled",
  "job.queued",
  "job.started",
  "job.completed",
  "job.failed",
  "job.cancelled",
  "stream.resync_required",
  "heartbeat",
  "document.page_started",
  "document.page_completed",
  "document.completed",
]);
export type ProgressEventType = z.infer<typeof zProgressEventType>;

export const zJobStatus = z.enum(["queued", "running", "completed", "cancelled", "failed"]);

export const zProgressEvent = z.object({
  document_id: z.string().nullish(),
  document_status: zDocumentStatus.nullish(),
  event: zProgressEventType,
  event_id: z.string(),
  event_sequence: z.int().gte(1),
  job_id: z.string().nullish(),
  job_status: zJobStatus.nullish(),
  message: z.string().nullish(),
  page_number: z.int().gte(1).nullish(),
  pages_completed: z.int().gte(0).nullish(),
  pages_total: z.int().gte(0).nullish(),
  percent: z.int().gte(0).lte(100).nullish(),
  overall_percent: z.number().gte(0).lte(65).nullish(),
  major_phase: z.string().nullish(),
  major_phase_percent: z.number().gte(0).lte(100).nullish(),
  page_percent: z.number().gte(0).lte(100).nullish(),
  operation: z.string().nullish(),
  operation_status: z.string().nullish(),
  progress_kind: z.string().nullish(),
  queue_position: z.int().gte(1).nullish(),
  session_id: z.string(),
  stage: z.string().nullish(),
  timestamp: z.iso.datetime(),
  canonicalisation_method: z.string().nullish(),
  canonical_page_count: z.int().gte(0).nullish(),
  canonical_status: z.string().nullish(),
  elapsed_seconds: z.number().gte(0).nullish(),
  document_elapsed_seconds: z.number().gte(0).nullish(),
  page_elapsed_seconds: z.number().gte(0).nullish(),
  operation_elapsed_seconds: z.number().gte(0).nullish(),
  stage_elapsed_seconds: z.number().gte(0).nullish(),
  deadline_remaining_seconds: z.number().gte(0).nullish(),
  worker_generation: z.int().gte(0).nullish(),
  worker_restart_count: z.int().gte(0).nullish(),
  attempt_number: z.int().gte(1).nullish(),
  max_attempts: z.int().gte(1).nullish(),
  reason_code: z.string().nullish(),
  reason_codes: z.array(z.string()).nullish(),
});
export type ProgressEvent = z.infer<typeof zProgressEvent>;

// ---------------------------------------------------------------------------
// SessionSnapshot — same shape as the generated contract, but with
// `documents`, `counts` and `recent_events` widened to the extended schemas
// above so a real Phase 2 backend response parses successfully instead of
// throwing (the generated `zDocumentStatus` enum rejects `"canonicalising"`
// outright).
// ---------------------------------------------------------------------------

export const zSessionStatus = z.enum([
  "created",
  "accepting_uploads",
  "queued",
  "processing",
  "ready",
  "reset",
  "expired",
  "failed",
  "deleted",
]);
export type SessionStatus = z.infer<typeof zSessionStatus>;

export const zSessionSnapshot = z.object({
  session_id: z.string(),
  status: zSessionStatus,
  created_at: z.iso.datetime(),
  last_activity_at: z.iso.datetime(),
  expires_at: z.iso.datetime(),
  expiring: z.boolean().default(false),
  seconds_remaining: z.int().gte(0),
  limits: zSessionLimits,
  runtime_warning: z.string(),
  counts: zDocumentStatusCounts,
  accepted_bytes: z.int().gte(0),
  known_pages: z.int().gte(0),
  unknown_page_documents: z.int().gte(0),
  queue: zQueueInfo,
  documents: z.array(zDocumentSummary),
  jobs: z.array(zJobSummary),
  recent_events: z.array(zProgressEvent),
});
export type SessionSnapshot = z.infer<typeof zSessionSnapshot>;

export const zProcessResponse = z.object({
  ignored: z.array(z.object({ document_id: z.string(), reason: z.string() })),
  queued: z.array(zJobSummary),
  session: zSessionSnapshot,
});
export type ProcessResponse = z.infer<typeof zProcessResponse>;

export const zUploadBatchResponse = z.object({
  accepted: z.array(zDocumentSummary),
  rejected: z.array(zRejectedDocument),
  session: zSessionSnapshot,
});
export type UploadBatchResponse = z.infer<typeof zUploadBatchResponse>;

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

function canonicalBasePath(sessionId: string, documentId: string): string {
  return `${sessionPath(sessionId)}/documents/${documentId}/canonical`;
}

// Absolute URL for the canonical PDF binary itself. PDF.js performs its own
// fetch (with Range support) against this URL — it is never routed through
// `getJson`, which only handles JSON bodies.
export function canonicalPdfUrl(sessionId: string, documentId: string): string {
  return `${environment.apiBaseUrl}${canonicalBasePath(sessionId, documentId)}`;
}

export function getCanonicalMetadata(
  sessionId: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<CanonicalDocumentMetadata> {
  return getJson(`${canonicalBasePath(sessionId, documentId)}/metadata`, {
    schema: zCanonicalDocumentMetadata,
    signal,
  });
}

export function getOverlayProof(
  sessionId: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<OverlayProofResponse> {
  return getJson(`${canonicalBasePath(sessionId, documentId)}/overlay-proof`, {
    schema: zOverlayProofResponse,
    signal,
  });
}

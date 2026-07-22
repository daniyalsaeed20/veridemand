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

export const MAX_PHASE2_PROGRESS_PERCENT = 15;

export const zDocumentStatus = z.enum([
  "uploaded",
  "queued",
  "canonicalising",
  "ready_for_extraction",
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
  progress_percent: z.int().gte(0).lte(MAX_PHASE2_PROGRESS_PERCENT),
  result_available: z.boolean().default(false),
  extraction_performed: z.boolean().default(false),
  warning_count: z.int().gte(0).default(0),
  queue_position: z.int().gte(1).nullish(),
  active_job_id: z.string().nullish(),
  created_at: z.iso.datetime(),
  canonical_status: zCanonicalStatus.nullish(),
  canonicalisation_method: zCanonicalisationMethod.nullish(),
  canonical_view_available: z.boolean().default(false),
  canonical_view_url: z.string().nullish(),
  canonical_metadata_url: z.string().nullish(),
});
export type DocumentSummary = z.infer<typeof zDocumentSummary>;

export const zDocumentStatusCounts = z.object({
  uploaded: z.int().gte(0).default(0),
  queued: z.int().gte(0).default(0),
  canonicalising: z.int().gte(0).default(0),
  ready_for_extraction: z.int().gte(0).default(0),
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
  queue_position: z.int().gte(1).nullish(),
  session_id: z.string(),
  stage: z.string().nullish(),
  timestamp: z.iso.datetime(),
  canonicalisation_method: z.string().nullish(),
  canonical_page_count: z.int().gte(0).nullish(),
  canonical_status: z.string().nullish(),
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

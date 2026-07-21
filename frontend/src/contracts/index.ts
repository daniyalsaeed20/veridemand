// Public contract surface for the frontend.
//
// Re-exports generated (never hand-maintained) TypeScript types and Zod v4
// schemas derived from the committed OpenAPI document. Import contracts from
// here rather than reaching into `./generated` directly.

export type {
  ApiErrorDetail,
  ApiErrorEnvelope,
  CheckState,
  DependencyCheck,
  DocumentFormat,
  DocumentListResponse,
  DocumentStatus,
  DocumentStatusCounts,
  DocumentSummary,
  IgnoredDocument,
  JobListResponse,
  JobStatus,
  JobSummary,
  LivenessResponse,
  PageCountStatus,
  ProcessRequest,
  ProcessResponse,
  ProgressEvent,
  ProgressEventType,
  QueueInfo,
  ReadinessResponse,
  RejectedDocument,
  SessionLimits,
  SessionSnapshot,
  SessionStatus,
  UploadBatchResponse,
} from "./generated/types.gen";

export {
  zApiErrorDetail,
  zApiErrorEnvelope,
  zCheckState,
  zDependencyCheck,
  zDocumentListResponse,
  zDocumentStatus,
  zDocumentSummary,
  zJobListResponse,
  zJobStatus,
  zJobSummary,
  zLivenessResponse,
  zProcessResponse,
  zProgressEvent,
  zProgressEventType,
  zReadinessResponse,
  zSessionSnapshot,
  zSessionStatus,
  zUploadBatchResponse,
} from "./generated/zod.gen";

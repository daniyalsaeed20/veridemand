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
  LivenessResponse,
  ReadinessResponse,
} from "./generated/types.gen";

export {
  zApiErrorDetail,
  zApiErrorEnvelope,
  zCheckState,
  zDependencyCheck,
  zLivenessResponse,
  zReadinessResponse,
} from "./generated/zod.gen";

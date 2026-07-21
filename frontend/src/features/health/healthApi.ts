import { getJson } from "../../api/http";
import type { LivenessResponse, ReadinessResponse } from "../../contracts";
import { zLivenessResponse, zReadinessResponse } from "../../contracts";

export function fetchLiveness(signal?: AbortSignal): Promise<LivenessResponse> {
  return getJson("/health/live", { schema: zLivenessResponse, signal });
}

export function fetchReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  return getJson("/health/ready", { schema: zReadinessResponse, signal });
}

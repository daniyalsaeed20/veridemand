/**
 * Frontend health contract — re-exports generated Zod and inferred type.
 * Field shapes come from backend JSON Schema via codegen; do not hand-edit shapes.
 */
import { z } from "zod";
import { HealthResponseSchema as GeneratedHealthResponseSchema } from "./generated/HealthResponse";

// Generated schema may be loose (json-schema-to-zod). Tighten wire validation here.
export const HealthResponseSchema = GeneratedHealthResponseSchema.and(
  z.object({
    status: z.enum(["ok", "degraded", "error"]),
    api_version: z.string(),
    app_version: z.string().nullable().optional(),
    contracts_version: z.string(),
    time_utc: z.string(),
    message: z.string().nullable().optional(),
  }),
);

export type HealthResponse = z.infer<typeof HealthResponseSchema>;

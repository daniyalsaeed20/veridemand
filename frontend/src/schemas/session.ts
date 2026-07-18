/**
 * CaseSession contract — generated Zod + tightened wire validation.
 */
import { z } from "zod";
import { CaseSessionSchema as Generated } from "./generated/CaseSession";

export const CaseSessionSchema = Generated.and(
  z.object({
    id: z.string().startsWith("ses_"),
    created_at: z.string(),
    expires_at: z.string(),
    last_activity_at: z.string(),
    status: z.string(),
    settings: z.record(z.string(), z.unknown()).optional(),
    warning: z.string().nullable().optional(),
  }),
);

export type CaseSession = z.infer<typeof CaseSessionSchema>;

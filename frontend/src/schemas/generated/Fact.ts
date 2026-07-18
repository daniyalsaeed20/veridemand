/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const FactSchema = z.object({ "confidence": z.number().gte(0).lte(1), "criticality": z.union([z.enum(["critical","normal"]), z.null()]).default(null), "description": z.union([z.string(), z.null()]).default(null), "display_value": z.union([z.string(), z.null()]).default(null), "document_ids": z.union([z.array(z.string()), z.null()]).default(null), "extraction_methods": z.array(z.string()).optional(), "fact_type": z.string(), "id": z.string(), "label_context": z.union([z.string(), z.null()]).default(null), "normalized_value": z.union([z.string(), z.number(), z.number().int(), z.null()]).default(null), "provenance": z.union([z.enum(["deterministic","calculated","user","llm_optional"]), z.null()]).default("deterministic"), "raw_value": z.string(), "session_id": z.string(), "source_span_ids": z.array(z.string()).optional(), "status": z.any(), "user_override": z.union([z.any(), z.null()]).default(null) }).strict()


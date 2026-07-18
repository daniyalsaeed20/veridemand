/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const SourceSpanSchema = z.object({ "confidence": z.union([z.number().gte(0).lte(1), z.null()]).default(null), "context": z.union([z.string(), z.null()]).default(null), "document_id": z.string(), "id": z.string(), "method": z.any(), "page_number": z.number().int().gte(1), "polygons": z.array(z.array(z.array(z.number())).min(3)), "text": z.string(), "token_ids": z.array(z.string()).optional() }).strict()


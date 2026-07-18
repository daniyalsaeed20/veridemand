/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const SourceTokenSchema = z.object({ "confidence": z.number().gte(0).lte(1), "document_id": z.string(), "id": z.string(), "method": z.any(), "page_number": z.number().int().gte(1), "polygon": z.array(z.array(z.number())).min(3), "text": z.string() }).strict()


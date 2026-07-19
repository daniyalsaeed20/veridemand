/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const ProcessEventSchema = z.object({ "document_id": z.union([z.string(), z.null()]).default(null), "error_code": z.union([z.string(), z.null()]).default(null), "event": z.string(), "message": z.union([z.string(), z.null()]).default(null), "page_number": z.union([z.number().int().gte(1), z.null()]).default(null), "progress": z.union([z.number().gte(0).lte(1), z.null()]).default(null), "sequence": z.number().int().gte(0), "session_id": z.string(), "status": z.union([z.string(), z.null()]).default(null) }).strict()

